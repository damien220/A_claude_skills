"""Tests for run_linters.py, validate_report.py, lint_skill.py and the maintainer scripts.

    python verification/test_scripts.py

Standard library only. Tests that need ruff or mypy read their paths from AUDITLINE_RUFF and
AUDITLINE_MYPY (or find them on PATH) and are skipped when a tool is missing. The jsonschema
cross-check runs only when that package is importable.
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


RL = load("run_linters", ROOT / "tooling" / "run_linters.py")
VR = load("validate_report", ROOT / "verification" / "validate_report.py")
SC = load("score", ROOT / "verification" / "score.py")
SCHEMA = json.loads(
    (ROOT / "tooling" / "finding.schema.json").read_text(encoding="utf-8")
)
SAMPLE = json.loads(
    (ROOT / "verification" / "python" / "sample_report.json").read_text(
        encoding="utf-8"
    )
)
RUFF = os.environ.get("AUDITLINE_RUFF") or shutil.which("ruff")
MYPY = os.environ.get("AUDITLINE_MYPY") or shutil.which("mypy")


def run_script(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter, repo-local scripts
        [PY, "-I", *args], capture_output=True, text=True, cwd=cwd, check=False
    )


class DiffParsing(unittest.TestCase):
    DIFF = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1,2 +1,3 @@\n@@ -10 +11 @@\n@@ -20,3 +22,0 @@\n"
        "diff --git a/new.py b/new.py\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n"
        "diff --git a/old.py b/old.py\n--- a/old.py\n+++ /dev/null\n@@ -1,4 +0,0 @@\n"
    )

    def test_changed_lines(self) -> None:
        got = RL.parse_changed_lines(self.DIFF)
        self.assertEqual(
            got["a.py"], {1, 2, 3, 11}
        )  # the pure deletion (count 0) adds no line
        self.assertEqual(got["new.py"], {1, 2})
        self.assertNotIn("old.py", got)


class ToolOutputParsing(unittest.TestCase):
    def test_mypy_line(self) -> None:
        m = RL.MYPY_LINE.match(
            'src/a.py:12: error: Value of type "X | None" is not indexable  [index]'
        )
        assert m
        self.assertEqual(
            (m.group("file"), m.group("line"), m.group("code")),
            ("src/a.py", "12", "index"),
        )

    def test_mypy_note_is_ignored(self) -> None:
        self.assertIsNone(RL.MYPY_LINE.match("src/a.py:12: note: Use X"))

    def test_tsc_line(self) -> None:
        m = RL.TSC_LINE.match(
            "src/a.ts(7,3): error TS2835: Relative import paths need explicit file extensions"
        )
        assert m
        self.assertEqual((m.group("line"), m.group("code")), ("7", "TS2835"))


class TscExitCodes(unittest.TestCase):
    """tsc reports diagnostics with exit 1 in some releases and 2 in others; both must be read."""

    OUT = (
        "a.tsx(3,7): error TS2322: Type 'string' is not assignable to type 'number'.\n"
    )

    def run_with(self, code: int, stdout: str) -> Any:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tsconfig.json").write_text("{}", encoding="utf-8")
            fake = subprocess.CompletedProcess([], code, stdout, "")
            original = RL.run
            RL.run = lambda *_a, **_k: fake
            try:
                return RL.run_tsc(Path(tmp), "tsc")
            finally:
                RL.run = original

    def test_exit_1_and_2_with_diagnostics_are_read(self) -> None:
        for code in (1, 2):
            tr = self.run_with(code, self.OUT)
            self.assertEqual((tr.status, len(tr.issues)), ("ran", 1), code)
            self.assertEqual(tr.issues[0].code, "TS2322")

    def test_a_crash_without_diagnostics_is_skipped(self) -> None:
        for code in (1, 2, 126):
            self.assertEqual(self.run_with(code, "boom").status, "skipped", code)

    def test_a_clean_run_reports_nothing(self) -> None:
        tr = self.run_with(0, "")
        self.assertEqual((tr.status, tr.issues), ("ran", []))


class EslintIgnored(unittest.TestCase):
    """ESLint answers "File ignored" per file when no config block matches; that is not a clean run."""

    @staticmethod
    def ignored(name: str) -> dict[str, Any]:
        msg = {
            "ruleId": None,
            "severity": 1,
            "message": "File ignored because no matching configuration was supplied.",
        }
        return {"filePath": f"/r/{name}", "messages": [msg]}

    def run_with(self, data: list[dict[str, Any]]) -> Any:
        fake = subprocess.CompletedProcess([], 0, json.dumps(data), "")
        original = RL.run
        RL.run = lambda *_a, **_k: fake
        try:
            return RL.run_eslint(Path("/r"), ["a.tsx", "b.tsx"], "eslint")
        finally:
            RL.run = original

    def test_every_file_ignored_is_a_skip(self) -> None:
        tr = self.run_with([self.ignored("a.tsx"), self.ignored("b.tsx")])
        self.assertEqual(tr.status, "skipped")
        self.assertIn("ignored every file", tr.note)

    def test_some_files_ignored_still_runs_and_says_so(self) -> None:
        clean = {"filePath": "/r/a.tsx", "messages": []}
        tr = self.run_with([clean, self.ignored("b.tsx")])
        self.assertEqual(tr.status, "ran")
        self.assertIn("1 of 2 files ignored", tr.note)

    def test_a_clean_run_is_unchanged(self) -> None:
        tr = self.run_with([{"filePath": "/r/a.tsx", "messages": []}])
        self.assertEqual((tr.status, tr.issues), ("ran", []))


class Mapping(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "a.py").write_text(
            "x = 1\ntry:\n    f()\nexcept Exception:\n    pass\n", encoding="utf-8"
        )
        self.map = RL.load_map()
        self.langs = {"a.py": "python"}

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(
        self,
        issues: list[Any],
        scope: dict[str, set[int] | None],
        security_only: bool = False,
    ) -> Any:
        run = RL.ToolRun("ruff", "ran", "", issues)
        return RL.build_findings(
            self.tmp, [run], scope, self.langs, self.map, security_only
        )

    def test_same_line_codes_merge_into_one_finding(self) -> None:
        issues = [
            RL.Issue("ruff", "a.py", 4, "S110", "try-except-pass"),
            RL.Issue("ruff", "a.py", 4, "BLE001", "blind except"),
        ]
        built = self.build(issues, {"a.py": None})
        findings, unmapped = built.findings, built.unmapped
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "PY-ERR-01")
        self.assertEqual(findings[0]["tool_code"], "BLE001, S110")
        self.assertEqual(findings[0]["evidence"], "except Exception:")
        self.assertEqual(unmapped, [])

    def test_unchanged_lines_are_dropped(self) -> None:
        built = self.build([RL.Issue("ruff", "a.py", 4, "S110", "m")], {"a.py": {1, 2}})
        self.assertEqual(built.findings, [])
        self.assertEqual(built.dropped[0]["reason"], "line not changed")

    def test_unknown_code_is_unmapped_not_forced(self) -> None:
        built = self.build([RL.Issue("ruff", "a.py", 1, "ZZZ999", "m")], {"a.py": None})
        self.assertEqual((built.findings, len(built.unmapped)), ([], 1))

    def test_security_only_keeps_primary_security_rules(self) -> None:
        issues = [
            RL.Issue("ruff", "a.py", 3, "S608", "sql"),
            RL.Issue("ruff", "a.py", 4, "S110", "swallowed"),
            RL.Issue("ruff", "a.py", 1, "F401", "unused"),
        ]
        built = self.build(issues, {"a.py": None}, security_only=True)
        self.assertEqual([f["rule_id"] for f in built.findings], ["PY-SEC-01"])
        # S110 is a security finding only if the swallowed error is a failed check
        self.assertEqual([c["rule_id"] for c in built.candidates], ["PY-SEC-24"])
        self.assertEqual([d["code"] for d in built.dropped], ["F401"])

    def test_python_tools_never_map_to_node_rules(self) -> None:
        for code, ids in self.map["codes"]["ruff"].items():
            self.assertTrue(all(i.startswith(("PY-", "X-")) for i in ids), code)

    def test_findings_validate_against_the_schema(self) -> None:
        issues = [
            RL.Issue("ruff", "a.py", 4, "S110", "m"),
            RL.Issue("ruff", "a.py", 1, "F401", "m"),
        ]
        findings = self.build(issues, {"a.py": None}).findings
        counts = {
            s: sum(1 for f in findings if f["severity"] == s) for s in VR.SEVERITIES
        }
        verdict = (
            "request changes"
            if counts["blocker"] or counts["major"]
            else "approve with nits"
        )
        report = {
            "verdict": verdict,
            "mode": "full",
            "scope": {"kind": "file", "files": ["a.py"]},
            "findings": findings,
            "summary": counts,
        }
        self.assertEqual(VR.check(report, SCHEMA, SCHEMA), [])


class ReportValidator(unittest.TestCase):
    def bad(self, mutate: Callable[[dict[str, Any]], object]) -> list[str]:
        report = copy.deepcopy(SAMPLE)
        mutate(report)
        errs: list[str] = VR.check(report, SCHEMA, SCHEMA)
        if not errs:
            errs = VR.gate(
                report,
                ROOT / "verification" / "python",
                True,
                set(RL.load_map()["rules"]),
            )
        return errs

    def test_sample_report_passes(self) -> None:
        self.assertEqual(self.bad(lambda r: None), [])

    def test_wrong_verdict(self) -> None:
        self.assertTrue(self.bad(lambda r: r.update(verdict="approve")))

    def test_summary_mismatch(self) -> None:
        self.assertTrue(
            self.bad(lambda r: r["summary"].update(nit=r["summary"]["nit"] + 1))
        )

    def test_duplicate_finding(self) -> None:
        def dup(r: dict[str, Any]) -> None:
            r["findings"].append(copy.deepcopy(r["findings"][0]))
            r["summary"][r["findings"][0]["severity"]] += 1

        self.assertTrue(any("duplicate" in e for e in self.bad(dup)))

    def test_evidence_must_match_the_line(self) -> None:
        self.assertTrue(
            any(
                "evidence" in e
                for e in self.bad(
                    lambda r: r["findings"][0].update(evidence="nothing like it")
                )
            )
        )

    def test_unknown_rule_id(self) -> None:
        self.assertTrue(
            self.bad(lambda r: r["findings"][0].update(rule_id="PY-ZZZ-99"))
        )

    def test_unsorted_findings(self) -> None:
        self.assertTrue(
            any("sorted" in e for e in self.bad(lambda r: r["findings"].reverse()))
        )

    def test_model_nit_cap(self) -> None:
        def many(r: dict[str, Any]) -> None:
            base = next(f for f in r["findings"] if f["severity"] == "nit")
            for i in range(6):
                extra = copy.deepcopy(base)
                extra.update(
                    source="model", line=base["line"] + i + 1, evidence=base["evidence"]
                )
                r["findings"].append(extra)
                r["summary"]["nit"] += 1

        self.assertTrue(
            any("model nits" in e or "evidence" in e for e in self.bad(many))
        )

    def test_security_only_rejects_other_rules(self) -> None:
        self.assertTrue(self.bad(lambda r: r.update(mode="security-only")))

    def test_pre_existing_is_not_counted(self) -> None:
        def pre(r: dict[str, Any]) -> None:
            r["findings"][0]["pre_existing"] = True

        self.assertTrue(
            self.bad(pre)
        )  # the summary still counts it, so the gate objects

    def test_agrees_with_jsonschema(self) -> None:
        try:
            jsonschema = importlib.import_module("jsonschema")
        except ImportError:
            self.skipTest("jsonschema not installed")
        mutations: list[Callable[[dict[str, Any]], object]] = [
            lambda r: None,
            lambda r: r.update(verdict="approve"),
            lambda r: r["findings"][0].update(rule_id="bad"),
            lambda r: r["findings"][0].update(extra=1),
            lambda r: r["findings"][0].pop("cite"),
            lambda r: r["summary"].update(major=-1),
            lambda r: r.update(mode="security-only"),
            lambda r: r["scope"].update(kind="diff"),
            lambda r: r["findings"][0].update(line=0),
            lambda r: r["findings"][0].update(title="x" * 121),
        ]
        validator = jsonschema.Draft202012Validator(SCHEMA)
        for i, mutate in enumerate(mutations):
            report = copy.deepcopy(SAMPLE)
            mutate(report)
            self.assertEqual(
                not VR.check(report, SCHEMA, SCHEMA),
                validator.is_valid(report),
                f"mutation {i}",
            )


def defect(
    i: str, line: int, cat: str, sev: str, tier: str = "standard"
) -> dict[str, Any]:
    return {
        "id": i,
        "line": line,
        "category": cat,
        "severity": sev,
        "tier": tier,
        "title": i,
    }


def finding(
    line: int, sev: str, cat: str = "", rule_id: str = "", file: str = "a.py"
) -> Any:
    raw: dict[str, Any] = {"file": file, "line": line, "severity": sev, "title": "t"}
    if cat:
        raw["category"] = cat
    if rule_id:
        raw["rule_id"] = rule_id
    return raw


def find_all(raws: list[dict[str, Any]]) -> list[Any]:
    return [
        SC.Finding(i, r, SC.category_of(r), r["file"], r["line"], r["severity"])
        for i, r in enumerate(raws)
    ]


class Scorer(unittest.TestCase):
    EXPECTED: dict[str, Any] = {
        "files": {
            "a.py": {
                "defects": [
                    defect("D1", 10, "security", "blocker", "hard"),
                    defect("D2", 11, "maintainability", "nit"),
                ],
                "decoys": [{"line": 20}],
            },
            "clean.py": {"defects": [], "decoys": []},
        }
    }

    def run_score(self, raws: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
        result: dict[str, Any] = SC.score(self.EXPECTED, find_all(raws), **kw)
        return result

    def test_nearby_finding_of_the_wrong_category_does_not_steal_a_defect(self) -> None:
        # greedy matching in finding order would give D1 to the maintainability finding
        r = self.run_score(
            [finding(10, "nit", "maintainability"), finding(11, "blocker", "security")]
        )
        self.assertEqual(r["matched"], 2)
        self.assertEqual(r["category_mismatches"], 0)
        self.assertEqual(
            r["severity_exact"], 1.0
        )  # each finding paired with its own defect

    def test_category_is_read_from_the_rule_id(self) -> None:
        r = self.run_score([finding(10, "blocker", rule_id="PY-SEC-01")])
        self.assertEqual((r["matched"], r["category_mismatches"]), (1, 0))

    def test_wrong_category_matches_only_when_allowed(self) -> None:
        raws = [finding(10, "major", "correctness")]
        self.assertEqual(self.run_score(raws)["category_mismatches"], 1)
        self.assertEqual(self.run_score(raws, strict=True)["matched"], 0)

    def test_one_finding_matches_one_defect(self) -> None:
        r = self.run_score([finding(10, "blocker", "security")])
        self.assertEqual((r["matched"], r["extras"]), (1, 0))
        self.assertEqual([m["id"] for m in r["missed"]], ["D2"])

    def test_decoy_hit_is_a_false_positive_but_a_nit_is_not(self) -> None:
        self.assertEqual(
            self.run_score([finding(20, "major", "correctness")])[
                "decoy_false_positives"
            ],
            1,
        )
        self.assertEqual(
            self.run_score([finding(20, "nit", "maintainability")])[
                "decoy_false_positives"
            ],
            0,
        )

    def test_blocker_in_a_clean_file_fails_the_control_gate(self) -> None:
        r = self.run_score([finding(5, "major", "correctness", file="clean.py")])
        self.assertEqual(r["control_blocker_major"], 1)
        self.assertFalse(r["meets"]["control_blocker_major"])

    def test_security_only_slice(self) -> None:
        r = self.run_score(
            [finding(10, "blocker", "security"), finding(11, "nit", "maintainability")],
            security_only=True,
        )
        self.assertEqual(
            (r["defects"], r["matched"], r["out_of_scope_reported"]), (1, 1, 1)
        )
        self.assertFalse(r["meets"]["out_of_scope_reported"])

    def test_scoring_the_same_findings_twice_gives_the_same_answer(self) -> None:
        found = find_all([finding(10, "blocker", "security")])
        full = SC.score(self.EXPECTED, found)
        sec = SC.score(self.EXPECTED, found, security_only=True)
        self.assertEqual((full["matched"], sec["matched"]), (1, 1))
        self.assertEqual(SC.score(self.EXPECTED, found)["matched"], 1)

    def test_recall_by_tier(self) -> None:
        r = self.run_score([finding(10, "blocker", "security")])
        self.assertEqual(r["recall_by_tier"]["hard"]["recall"], 1.0)
        self.assertEqual(r["recall_by_tier"]["standard"]["recall"], 0.0)

    def test_pre_existing_findings_are_not_scored(self) -> None:
        raw = finding(10, "blocker", "security")
        raw["pre_existing"] = True
        self.assertEqual(self.run_score([raw])["matched"], 0)

    def test_filtered_findings_do_not_misalign_the_matching(self) -> None:
        unknown = finding(
            10, "major", "security", file="elsewhere.py"
        )  # not in the corpus
        old = finding(10, "major", "security")
        old["pre_existing"] = True
        real = finding(10, "blocker", "security")
        r = self.run_score([unknown, old, real, finding(11, "nit", "maintainability")])
        self.assertEqual((r["matched"], r["severity_exact"]), (2, 1.0))
        sec = self.run_score(
            [unknown, old, finding(11, "nit", "maintainability"), real],
            security_only=True,
        )
        self.assertEqual((sec["matched"], sec["out_of_scope_reported"]), (1, 1))

    EVIDENCE_EXPECTED: dict[str, Any] = {
        "files": {
            "a.py": {
                "defects": [
                    {
                        **defect("D1", 100, "security", "blocker"),
                        "evidence": "conn.execute(f'SELECT * FROM t WHERE id={uid}')",
                    },
                    {**defect("D2", 130, "correctness", "major"), "evidence": "}"},
                ],
                "decoys": [],
            }
        }
    }

    def run_evidence(self, raws: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
        result: dict[str, Any] = SC.score(self.EVIDENCE_EXPECTED, find_all(raws), **kw)
        return result

    def test_a_finding_inside_a_defect_span_matches(self) -> None:
        expected = json.loads(json.dumps(self.EVIDENCE_EXPECTED))
        expected["files"]["a.py"]["defects"][0]["span"] = [90, 100]
        inside = finding(92, "blocker", "security")  # no quote at all
        outside = finding(110, "blocker", "security")
        hit = SC.score(expected, find_all([inside]))
        self.assertEqual((hit["matched"], hit["extras"]), (1, 0))
        self.assertEqual(SC.score(expected, find_all([outside]))["matched"], 0)

    def test_a_quote_that_matches_counts_even_when_the_line_is_off(self) -> None:
        raw = finding(112, "blocker", "security")
        raw["evidence"] = "  conn.execute(f'SELECT * FROM t WHERE id={uid}')  "
        r = self.run_evidence([raw])
        self.assertEqual((r["matched"], r["extras"]), (1, 0))
        self.assertEqual(self.run_evidence([raw], window=0)["matched"], 0)

    def test_a_quote_inside_a_longer_quote_matches(self) -> None:
        raw = finding(95, "blocker", "security")
        raw["evidence"] = (
            "rows = conn.execute(f'SELECT * FROM t WHERE id={uid}')\n    return rows"
        )
        self.assertEqual(self.run_evidence([raw])["matched"], 1)

    def test_a_quote_too_far_away_or_too_short_does_not_match(self) -> None:
        far = finding(300, "blocker", "security")
        far["evidence"] = "conn.execute(f'SELECT * FROM t WHERE id={uid}')"
        short = finding(131 + 5, "major", "correctness")
        short["evidence"] = "}"  # defect D2 quotes a bare brace: never matched by text
        self.assertEqual(self.run_evidence([far, short])["matched"], 0)

    def test_the_line_match_still_wins_over_a_distant_quote(self) -> None:
        near = finding(101, "blocker", "security")
        far = finding(120, "blocker", "security")
        far["evidence"] = "conn.execute(f'SELECT * FROM t WHERE id={uid}')"
        r = self.run_evidence([far, near])
        self.assertEqual((r["matched"], r["extras"]), (1, 1))
        self.assertEqual(r["extra_findings"][0]["line"], 120)

    def test_reproduces_the_recorded_baseline_recall(self) -> None:
        base = ROOT / "verification" / "baseline"
        expected = json.loads(
            (ROOT / "verification" / "python" / "expected.json").read_text(
                encoding="utf-8"
            )
        )
        old = json.loads(
            (base / "score_python_sonnet.json").read_text(encoding="utf-8")
        )
        new = SC.score(
            expected,
            SC.load_findings(base / "python_sonnet.json"),
            files=[
                "sample_bad_1.py",
                "sample_good_1.py",
            ],  # the files the baseline covered
        )
        # sample_bad_1.py gained D9 (idempotency key) after the baseline was recorded
        self.assertEqual(
            (new["matched"], new["defects"]), (old["matched"], old["defects"] + 1)
        )


@unittest.skipUnless(RUFF, "ruff not available")
class EndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp())
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        (self.repo / "app.py").write_text(
            "import os\n\n\ndef old(x=[]):\n    return x\n", encoding="utf-8"
        )
        self.git("add", ".")
        self.git("commit", "-qm", "base")

    def tearDown(self) -> None:
        shutil.rmtree(self.repo, ignore_errors=True)

    def git(self, *args: str) -> None:
        git = shutil.which("git") or "git"
        subprocess.run([git, *args], cwd=self.repo, check=True, capture_output=True)  # noqa: S603

    def lint(self, *args: str) -> dict[str, Any]:
        tools = [f"--tool=ruff={RUFF}"] + ([f"--tool=mypy={MYPY}"] if MYPY else [])
        done = run_script(
            str(ROOT / "tooling" / "run_linters.py"),
            "--root",
            str(self.repo),
            *tools,
            *args,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        result: dict[str, Any] = json.loads(done.stdout)
        return result

    def test_diff_scope_reports_only_changed_lines(self) -> None:
        (self.repo / "app.py").write_text(
            "import os\n\n\ndef old(x=[]):\n    return x\n\n\ndef new(y=[]):\n    print('debug')\n    return y\n",
            encoding="utf-8",
        )
        out = self.lint("--base", "HEAD")
        lines = {(f["line"], f["rule_id"]) for f in out["findings"]}
        self.assertIn((8, "PY-COR-01"), lines)
        self.assertIn((9, "PY-DIFF-01"), lines)
        self.assertNotIn(
            4, {ln for ln, _ in lines}
        )  # the old mutable default is on an unchanged line
        self.assertEqual(out["scope"]["kind"], "diff")
        self.assertEqual(out["tools"][0]["status"], "ran")

    def test_file_scope_reports_whole_file(self) -> None:
        out = self.lint("--files", "app.py")
        self.assertIn(4, {f["line"] for f in out["findings"]})
        self.assertIn("PY-MAINT-01", {f["rule_id"] for f in out["findings"]})

    def test_missing_tool_is_reported_as_skipped(self) -> None:
        done = run_script(
            str(ROOT / "tooling" / "run_linters.py"),
            "--root",
            str(self.repo),
            "--files",
            "app.py",
            f"--tool=ruff={RUFF}",
            "--tool=mypy=/nonexistent/mypy",
        )
        out = json.loads(done.stdout)
        mypy = next(t for t in out["tools"] if t["name"] == "mypy")
        self.assertEqual(mypy["status"], "skipped")

    def test_security_only_drops_non_security(self) -> None:
        (self.repo / "app.py").write_text(
            "import os\nq = f\"SELECT * FROM t WHERE a = '{input()}'\"\n",
            encoding="utf-8",
        )
        out = self.lint("--files", "app.py", "--security-only")
        self.assertTrue(all("-SEC-" in f["rule_id"] for f in out["findings"]))
        self.assertEqual(out["mode"], "security-only")


class ProjectScripts(unittest.TestCase):
    def test_lint_skill_passes(self) -> None:
        done = run_script(str(ROOT / "verification" / "lint_skill.py"))
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_corpus_ground_truth_is_valid(self) -> None:
        done = run_script(str(ROOT / "verification" / "check_corpus.py"))
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_generated_files_are_current(self) -> None:
        gen = ROOT / "maintainer" / "gen_checklists.py"
        if not gen.exists():
            self.skipTest("maintainer/ is not shipped")
        done = run_script(str(gen), "--check")
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_check_drift_runs(self) -> None:
        drift = ROOT / "maintainer" / "check_drift.py"
        if not drift.exists():
            self.skipTest("maintainer/ is not shipped")
        self.assertEqual(run_script(str(drift)).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
