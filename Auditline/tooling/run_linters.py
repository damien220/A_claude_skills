"""Run ruff, mypy, eslint and tsc on the files in scope; print schema-shaped findings.

Standard library only. Never installs or downloads a tool.

    python tooling/run_linters.py --base main            # diff against a base ref
    python tooling/run_linters.py --staged               # staged changes
    python tooling/run_linters.py --files src/app.py     # whole files, no diff
    python tooling/run_linters.py --base main --security-only

Prints one JSON object on stdout:

    tools      every relevant tool, "ran" or "skipped", with a note (report schema)
    findings   tool results mapped to a rule ID, merged per line (report schema, "finding")
    unmapped   tool results with no rule in tooling/tool_map.json, for the model to triage
    dropped    results left out, each with the reason
    candidates (--security-only) tool results whose primary rule is not a security rule but that
               become one in context (a print that logs a secret, a swallowed check, an auth
               check not awaited); the model promotes or discards each

Severity on a tool finding is provisional: it is the lowest level the rule defaults to, and the
reviewer raises it when the consequence on this code path calls for it
(refs/severity-and-output-format.md). Project config is used when present; otherwise the
configs in tooling/fallback/ are used.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL_MAP = HERE / "tool_map.json"
FALLBACK = HERE / "fallback"
TIMEOUT_S = 300
LEVEL_ORDER = ("nit", "minor", "major", "blocker")  # lowest first
TOOL_ORDER = ("ruff", "mypy", "eslint", "tsc")
PY_EXT = {".py"}
JS_EXT = {".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"}
JSX_EXT = {".tsx", ".jsx"}
BROWSER_IMPORT = re.compile(r"""from\s+['"](?:react|react-dom|next)(?:/[^'"]*)?['"]""")


@dataclass
class Issue:
    tool: str
    file: str
    line: int
    code: str
    message: str
    fix: str = ""


@dataclass
class Result:
    findings: list[dict[str, object]] = field(default_factory=list)
    unmapped: list[dict[str, object]] = field(default_factory=list)
    dropped: list[dict[str, object]] = field(default_factory=list)
    candidates: list[dict[str, object]] = field(default_factory=list)


@dataclass
class ToolRun:
    name: str
    status: str = "skipped"
    note: str = ""
    issues: list[Issue] = field(default_factory=list)


def git(root: Path, *args: str) -> str:
    exe = shutil.which("git")
    if exe is None:
        raise RuntimeError("git is not installed")
    done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [exe, *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT_S,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or f"git {' '.join(args)} failed")
    return done.stdout


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_changed_lines(diff: str) -> dict[str, set[int]]:
    """Map each file in a ``git diff -U0`` to the new-file line numbers it adds or changes."""
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = None if target == "/dev/null" else target.removeprefix("b/")
            if current is not None:
                changed.setdefault(current, set())
        elif current is not None and (m := HUNK.match(line)):
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            changed[current].update(range(start, start + count))
    return changed


def resolve_scope(
    root: Path, args: argparse.Namespace
) -> tuple[dict[str, set[int] | None], dict[str, object]]:
    """Return {file: changed lines or None for all} and the scope block of the report."""
    if args.files:
        files: dict[str, set[int] | None] = dict.fromkeys(args.files)
        return files, {"kind": "file", "files": sorted(files)}
    if args.base:
        merge_base = git(root, "merge-base", args.base, "HEAD").strip()
        diff = git(root, "diff", "-U0", "--no-color", "--diff-filter=d", merge_base)
        base = args.base
    else:
        diff = git(root, "diff", "--cached", "-U0", "--no-color", "--diff-filter=d")
        base = "staged"
        if not diff.strip() and not args.staged:
            diff = git(root, "diff", "-U0", "--no-color", "--diff-filter=d")
            base = "working tree"
    changed = parse_changed_lines(diff)
    scope: dict[str, object] = {"kind": "diff", "base": base, "files": sorted(changed)}
    return dict(changed.items()), scope


def language_of(root: Path, rel: str) -> str | None:
    ext = Path(rel).suffix
    if ext in PY_EXT:
        return "python"
    if ext in JSX_EXT:
        return "typescript"
    if ext in JS_EXT:
        try:
            head = (root / rel).read_text(encoding="utf-8", errors="replace")[:20000]
        except OSError:
            return None
        return (
            "typescript"
            if ext in {".ts", ".mts", ".cts"} and BROWSER_IMPORT.search(head)
            else "node"
        )
    return None


def find_exe(name: str, root: Path, overrides: dict[str, str]) -> str | None:
    if name in overrides:
        return overrides[name] if Path(overrides[name]).exists() else None
    local = root / "node_modules" / ".bin" / name
    if name in {"eslint", "tsc"} and local.exists():
        return str(local)
    return shutil.which(name)


def has_config(tool: str, root: Path) -> str | None:
    """Name of the project config for a tool, or None."""
    names = {
        "ruff": ("ruff.toml", ".ruff.toml"),
        "mypy": ("mypy.ini", ".mypy.ini"),
        "eslint": (
            "eslint.config.js",
            "eslint.config.mjs",
            "eslint.config.cjs",
            "eslint.config.ts",
            ".eslintrc",
            ".eslintrc.js",
            ".eslintrc.cjs",
            ".eslintrc.json",
            ".eslintrc.yml",
            ".eslintrc.yaml",
        ),
    }.get(tool, ())
    for n in names:
        if (root / n).exists():
            return n
    pyproject = root / "pyproject.toml"
    if (
        pyproject.exists()
        and tool in {"ruff", "mypy"}
        and re.search(
            rf"^\[tool\.{tool}[\].]", pyproject.read_text(encoding="utf-8"), re.M
        )
    ):
        return "pyproject.toml"
    setup_cfg = root / "setup.cfg"
    if (
        tool == "mypy"
        and setup_cfg.exists()
        and "[mypy" in setup_cfg.read_text(encoding="utf-8")
    ):
        return "setup.cfg"
    package_json = root / "package.json"
    if (
        tool == "eslint"
        and package_json.exists()
        and '"eslintConfig"' in package_json.read_text(encoding="utf-8")
    ):
        return "package.json"
    return None


def run(cmd: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - tool path resolved above, arguments are file names
        cmd, cwd=root, capture_output=True, text=True, check=False, timeout=TIMEOUT_S
    )


def first_line(text: str) -> str:
    for ln in text.splitlines():
        if ln.strip():
            return ln.strip()[:200]
    return "no output"


def rel_path(root: Path, raw: str) -> str:
    p = Path(raw)
    try:
        return (
            (p if p.is_absolute() else root / p).resolve().relative_to(root).as_posix()
        )
    except ValueError:
        return p.as_posix()


def run_ruff(root: Path, files: list[str], exe: str) -> ToolRun:
    tr = ToolRun("ruff")
    cfg = has_config("ruff", root)
    cmd = [exe, "check", "--output-format", "json", "--no-cache"]
    if cfg is None:
        cmd += ["--config", str(FALLBACK / "ruff.toml")]
    done = run([*cmd, *files], root)
    if done.returncode not in (0, 1):
        tr.note = f"exited {done.returncode}: {first_line(done.stderr)}"
        return tr
    try:
        data = json.loads(done.stdout or "[]")
    except json.JSONDecodeError:
        tr.note = f"unreadable output: {first_line(done.stdout)}"
        return tr
    for d in data:
        if not d.get("code"):
            continue  # syntax errors carry no code; the interpreter reports them
        fix = (d.get("fix") or {}).get("message") or ""
        tr.issues.append(
            Issue(
                "ruff",
                rel_path(root, d["filename"]),
                d["location"]["row"],
                d["code"],
                d["message"],
                fix,
            )
        )
    tr.status = "ran"
    tr.note = f"project config {cfg}" if cfg else "bundled fallback config"
    return tr


MYPY_LINE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+)(?::\d+)?: (?:error|warning): (?P<msg>.*?)(?:\s+\[(?P<code>[\w-]+)\])?$"
)


def run_mypy(root: Path, files: list[str], exe: str) -> ToolRun:
    tr = ToolRun("mypy")
    cfg = has_config("mypy", root)
    cmd = [
        exe,
        "--no-error-summary",
        "--show-error-codes",
        "--no-pretty",
        "--no-color-output",
    ]
    if cfg is None:
        cmd += ["--config-file", str(FALLBACK / "mypy.ini")]
    done = run([*cmd, *files], root)
    if done.returncode not in (0, 1):
        tr.note = f"exited {done.returncode}: {first_line(done.stderr or done.stdout)}"
        return tr
    for ln in done.stdout.splitlines():
        if (m := MYPY_LINE.match(ln)) and m.group("code"):
            tr.issues.append(
                Issue(
                    "mypy",
                    rel_path(root, m.group("file")),
                    int(m.group("line")),
                    m.group("code"),
                    m.group("msg"),
                )
            )
    tr.status = "ran"
    tr.note = (
        f"project config {cfg}" if cfg else "bundled fallback config (strict flags off)"
    )
    return tr


def run_eslint(root: Path, files: list[str], exe: str) -> ToolRun:
    tr = ToolRun("eslint")
    cfg = has_config("eslint", root)
    cmd = [exe, "-f", "json"]
    if cfg is None:
        cmd += ["--no-config-lookup", "-c", str(FALLBACK / "eslint.config.js")]
    done = run([*cmd, *files], root)
    if done.returncode not in (0, 1):
        tr.note = f"exited {done.returncode}: {first_line(done.stderr or done.stdout)}"
        return tr
    try:
        data = json.loads(done.stdout or "[]")
    except json.JSONDecodeError:
        tr.note = f"unreadable output: {first_line(done.stdout or done.stderr)}"
        return tr
    ignored = 0
    for f in data:
        for m in f.get("messages", []):
            if not m.get("ruleId") and str(m.get("message", "")).startswith(
                "File ignored"
            ):
                ignored += 1
            if m.get("ruleId"):
                tr.issues.append(
                    Issue(
                        "eslint",
                        rel_path(root, f["filePath"]),
                        m.get("line", 1),
                        m["ruleId"],
                        m["message"],
                    )
                )
    if data and ignored == len(data):
        # no config block matched any file: nothing was linted, so "no findings" would mislead
        tr.note = (
            "eslint ignored every file (no matching configuration; a plugin or parser that "
            "failed to load, such as typescript-eslint on an unsupported TypeScript, is the usual cause)"
        )
        return tr
    tr.status = "ran"
    tr.note = f"project config {cfg}" if cfg else "bundled fallback config"
    if ignored:
        tr.note += f"; {ignored} of {len(data)} files ignored by the configuration"
    return tr


TSC_LINE = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+),\d+\): error (?P<code>TS\d+): (?P<msg>.*)$"
)


def run_tsc(root: Path, exe: str) -> ToolRun:
    tr = ToolRun("tsc")
    if not (root / "tsconfig.json").exists():
        tr.note = "no tsconfig.json"
        return tr
    done = run([exe, "--noEmit", "--pretty", "false", "-p", "tsconfig.json"], root)
    # Release lines differ on the exit code for "diagnostics reported" (1 or 2): trust the output.
    if done.returncode not in (0, 1, 2) or (
        done.returncode and "error TS" not in done.stdout
    ):
        tr.note = f"exited {done.returncode}: {first_line(done.stderr or done.stdout)}"
        return tr
    for ln in done.stdout.splitlines():
        if m := TSC_LINE.match(ln):
            tr.issues.append(
                Issue(
                    "tsc",
                    rel_path(root, m.group("file")),
                    int(m.group("line")),
                    m.group("code"),
                    m.group("msg"),
                )
            )
    tr.status = "ran"
    tr.note = "project tsconfig.json"
    return tr


def load_map() -> dict[str, object]:
    return json.loads(TOOL_MAP.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def candidates(tool_map: dict[str, object], issue: Issue, language: str) -> list[str]:
    codes = tool_map["codes"]
    if not isinstance(codes, dict):
        return []
    ids: list[str] = codes.get(issue.tool, {}).get(issue.code, [])
    want = {"python": "PY-", "node": "NODE-", "typescript": "TS-"}[language]
    return [i for i in ids if i.startswith((want, "X-"))]


def provisional_severity(levels: Iterable[str]) -> str:
    known = [lv for lv in levels if lv in LEVEL_ORDER]
    return min(known, key=LEVEL_ORDER.index) if known else "minor"


def category(rule_id: str) -> str:
    return rule_id.split("-")[1]


def concept(rule_id: str) -> int:
    return int(rule_id.rsplit("-", 1)[1])


def read_line(root: Path, rel: str, n: int) -> str:
    try:
        lines = (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[n - 1].strip() if 0 < n <= len(lines) else ""
    except OSError:
        return ""


def build_findings(
    root: Path,
    runs: list[ToolRun],
    scope: dict[str, set[int] | None],
    langs: dict[str, str],
    tool_map: dict[str, object],
    security_only: bool,
) -> Result:
    rules = tool_map["rules"]
    if not isinstance(rules, dict):
        raise TypeError("tool map has no 'rules' table")
    groups: dict[tuple[str, int, str], list[tuple[Issue, str]]] = {}
    result = Result()

    def where(issue: Issue) -> dict[str, object]:
        return {
            "tool": issue.tool,
            "file": issue.file,
            "line": issue.line,
            "code": issue.code,
        }

    for tr in runs:
        for issue in tr.issues:
            lang = langs.get(issue.file)
            if issue.file not in scope or lang is None:
                result.dropped.append({**where(issue), "reason": "file not in scope"})
                continue
            changed = scope[issue.file]
            if changed is not None and issue.line not in changed:
                result.dropped.append({**where(issue), "reason": "line not changed"})
                continue
            cands = candidates(tool_map, issue, lang)
            if not cands:
                result.unmapped.append({**where(issue), "message": issue.message})
                continue
            if security_only and "-SEC-" not in cands[0]:
                # A result is a security finding only when its primary rule is a security rule.
                # A bare print, a blind except or a floating promise becomes one only when the
                # code around it makes it so (secrets printed, a failed check swallowed, an auth
                # check not awaited), which the model decides.
                sec = next((c for c in cands if "-SEC-" in c), None)
                if sec is None:
                    result.dropped.append(
                        {**where(issue), "reason": "security-only: not a security rule"}
                    )
                else:
                    result.candidates.append(
                        {
                            **where(issue),
                            "message": issue.message,
                            "rule_id": sec,
                            "title": str(rules[sec]["title"]),
                        }
                    )
                continue
            rid = cands[0]
            groups.setdefault((issue.file, issue.line, category(rid)), []).append(
                (issue, rid)
            )
    findings: list[dict[str, object]] = []
    for (file, line, _cat), items in sorted(groups.items()):
        rid = min((r for _, r in items), key=concept)
        main = min(
            items, key=lambda it: (TOOL_ORDER.index(it[0].tool), concept(it[1]))
        )[0]
        same_tool = sorted({i.code for i, _ in items if i.tool == main.tool})
        others = sorted({f"{i.tool} {i.code}" for i, _ in items if i.tool != main.tool})
        rule = rules[rid]
        why = f"{main.tool} {', '.join(same_tool)}: {main.message}"
        if others:
            why += f" (also reported by {', '.join(others)})"
        findings.append(
            {
                "severity": provisional_severity(rule["levels"]),
                "confidence": "high",
                "file": file,
                "line": line,
                "rule_id": rid,
                "title": str(rule["title"])[:120],
                "evidence": read_line(root, file, line) or main.message,
                "why": why,
                "fix": main.fix or str(rule["fix"]) or "See the rule in the ref.",
                "cite": str(rule["cite"]) or "See the rule in the ref.",
                "source": main.tool,
                "tool_code": ", ".join(same_tool),
                "pre_existing": False,
            }
        )
    result.findings = findings
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="project root (default: current directory)",
    )
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--base", help="review the diff against this ref (merge-base)")
    grp.add_argument("--staged", action="store_true", help="review staged changes only")
    grp.add_argument("--files", nargs="+", help="review whole files, no diff")
    ap.add_argument(
        "--security-only",
        action="store_true",
        help="keep only results that map to a -SEC- rule",
    )
    ap.add_argument(
        "--tool",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="use this executable for a tool",
    )
    ap.add_argument(
        "--max-unmapped", type=int, default=50, help="cap on the unmapped list"
    )
    args = ap.parse_args()

    root: Path = args.root.resolve()
    overrides = dict(t.split("=", 1) for t in args.tool)
    try:
        scope, scope_block = resolve_scope(root, args)
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    langs = {f: lang for f in scope if (lang := language_of(root, f))}
    present = set(langs.values())
    scope_block["languages"] = sorted(present)
    py_files = sorted(f for f, lg in langs.items() if lg == "python")
    js_files = sorted(f for f, lg in langs.items() if lg in {"node", "typescript"})

    runs: list[ToolRun] = []
    plan: list[tuple[str, list[str]]] = []
    if py_files:
        plan += [("ruff", py_files), ("mypy", py_files)]
    if js_files:
        plan += [("eslint", js_files), ("tsc", js_files)]
    for name, files in plan:
        exe = find_exe(name, root, overrides)
        if exe is None:
            runs.append(ToolRun(name, "skipped", "not installed"))
            continue
        try:
            if name == "ruff":
                runs.append(run_ruff(root, files, exe))
            elif name == "mypy":
                runs.append(run_mypy(root, files, exe))
            elif name == "eslint":
                runs.append(run_eslint(root, files, exe))
            else:
                runs.append(run_tsc(root, exe))
        except subprocess.TimeoutExpired:
            runs.append(ToolRun(name, "skipped", f"timed out after {TIMEOUT_S}s"))

    if args.security_only:
        for tr in runs:
            if tr.name in {"mypy", "tsc"} and tr.status == "ran":
                tr.note += "; results dropped in security-only mode unless they map to a -SEC- rule"

    built = build_findings(root, runs, scope, langs, load_map(), args.security_only)
    for tr in runs:
        n = sum(
            1
            for d in built.dropped
            if d["tool"] == tr.name and d["reason"] == "line not changed"
        )
        if n and tr.status == "ran":
            tr.note += f"; {n} results on unchanged lines dropped"
    out = {
        "mode": "security-only" if args.security_only else "full",
        "scope": scope_block,
        "tools": [
            {"name": t.name, "status": t.status, **({"note": t.note} if t.note else {})}
            for t in runs
        ],
        "findings": built.findings,
        "unmapped": built.unmapped[: args.max_unmapped],
        "dropped": built.dropped,
    }
    if args.security_only:
        out["candidates"] = built.candidates
    if len(built.unmapped) > args.max_unmapped:
        out["unmapped_truncated"] = len(built.unmapped) - args.max_unmapped
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
