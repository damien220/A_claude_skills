#!/usr/bin/env python3
"""Score reviewer findings against a language's expected.json. Standard library only.

    score.py EXPECTED FINDINGS [--tolerance N] [--security-only] [--files F ...]
                               [--strict-category] [--evidence-window N] [--summary]

FINDINGS is a report (``{"findings": [...]}``) or a bare list. A finding carries ``file``,
``line``, ``severity`` and either ``category`` or a ``rule_id`` (the category is read from the
rule ID: ``PY-SEC-01`` is security).

Matching is one to one and deterministic. Within a file, every (finding, defect) pair whose lines
are within ``--tolerance`` is a candidate, and so is a pair whose quoted evidence matches (see
below); candidates are taken in order of category agreement, then line distance, then file order. A finding of the wrong category can therefore only take a
defect that no finding of the right category claims, and is flagged ``category_mismatch``
(``--strict-category`` forbids it). A defect that is a pattern across several lines (acquire here, release there) may carry a
``span`` [first, last]; a finding inside it is a hit. Evidence match: a finding whose ``evidence`` contains the defect's ``evidence`` (or the reverse),
compared with whitespace collapsed and at least ``MIN_EVIDENCE`` characters long, matches that
defect even when the lines differ, provided they are within ``--evidence-window`` lines. A review
that quotes the right code but reports a nearby wrong line number is still a hit.
Findings left over are extras; those that sit on a decoy line
(correct code that looks wrong) are false positives.

``--security-only`` scores the security slice: only security defects are expected, and findings of
any other category are counted as ``out_of_scope_reported`` (should be 0).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MIN_EVIDENCE = 12  # shorter quotes (a bare brace, `return;`) match too many places
# an evidence match more than this many lines away is a different spot
EVIDENCE_WINDOW = 40
SEVERITIES = ("blocker", "major", "minor", "nit")
CATEGORY_OF = {
    "SEC": "security",
    "COR": "correctness",
    "ACC": "correctness",
    "ERR": "error-handling",
    "PERF": "performance",
    "TEST": "tests",
    "MAINT": "maintainability",
    "OPS": "maintainability",
    "DIFF": "diff-hygiene",
}
# Section 10 thresholds that can be checked mechanically. Precision needs a manual verdict on
# the extras, so only its lower bound is reported.
THRESHOLDS = {
    "recall_blocker_major": 0.90,
    "severity_exact": 0.75,
    "control_blocker_major": 0,
}


@dataclass
class Defect:
    file: str
    spec: dict[str, Any]
    matched_by: Finding | None = None

    @property
    def key(self) -> str:
        return f"{self.file}:{self.spec['id']}"

    @property
    def line(self) -> int:
        return int(self.spec["line"])

    def gap(self, line: int) -> int:
        """Lines between ``line`` and the defect: 0 inside its optional ``span`` [first, last]."""
        first, last = self.spec.get("span", (self.line, self.line))
        return max(first - line, line - last, 0)


@dataclass
class Finding:
    index: int
    raw: dict[str, Any]
    category: str
    file: str = ""
    line: int = 0
    severity: str = "minor"
    matched: Defect | None = None
    mismatch: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def category_of(raw: dict[str, Any]) -> str:
    if raw.get("category"):
        return str(raw["category"])
    rule = str(raw.get("rule_id", ""))
    parts = rule.split("-")
    return CATEGORY_OF.get(parts[1], "") if len(parts) == 3 else ""


def load_findings(path: Path, names: dict[str, str] | None = None) -> list[Finding]:
    """Read findings; ``names`` maps the file names a reviewer saw back to the corpus names."""
    data = json.loads(path.read_text(encoding="utf-8"))
    raws: list[dict[str, Any]] = data["findings"] if isinstance(data, dict) else data
    out: list[Finding] = []
    for i, raw in enumerate(raws):
        out.append(
            Finding(
                i,
                raw,
                category_of(raw),
                (names or {}).get(str(raw.get("file", "")), str(raw.get("file", ""))),
                int(raw.get("line", 0)),
                str(raw.get("severity", "minor")),
            )
        )
    return out


def squash(text: Any) -> str:
    return " ".join(str(text or "").split())


def same_evidence(finding: str, defect: str) -> bool:
    """True when one quote contains the other and the shorter is long enough to be specific."""
    a, b = squash(finding), squash(defect)
    short, long_ = sorted((a, b), key=len)
    return len(short) >= MIN_EVIDENCE and short in long_


def match(
    defects: list[Defect],
    findings: list[Finding],
    tolerance: int,
    strict: bool,
    window: int = EVIDENCE_WINDOW,
) -> None:
    pairs: list[tuple[int, int, int, int]] = []
    for i, f in enumerate(findings):
        for j, d in enumerate(defects):
            gap = d.gap(f.line)
            if f.file != d.file:
                continue
            if gap > tolerance and not (
                gap <= window
                and same_evidence(f.raw.get("evidence", ""), d.spec.get("evidence", ""))
            ):
                continue
            mismatch = int(f.category != d.spec["category"])
            if strict and mismatch:
                continue
            pairs.append((mismatch, gap, i, j))
    for mismatch, _gap, fi, dj in sorted(pairs):
        f, d = findings[fi], defects[dj]
        if f.matched is None and d.matched_by is None:
            f.matched, f.mismatch, d.matched_by = d, bool(mismatch), f


def ratio(num: int, den: int, empty: float = 1.0) -> float:
    return num / den if den else empty


def score(
    expected: dict[str, Any],
    findings: list[Finding],
    tolerance: int = 2,
    security_only: bool = False,
    strict: bool = False,
    files: list[str] | None = None,
    window: int = EVIDENCE_WINDOW,
) -> dict[str, Any]:
    for f in (
        findings
    ):  # a list may be scored more than once (full slice, then security-only)
        f.matched, f.mismatch = None, False
    specs = {
        name: spec
        for name, spec in expected["files"].items()
        if files is None or name in files
    }
    defects = [
        Defect(name, d)
        for name, spec in specs.items()
        for d in spec["defects"]
        if not security_only or d["category"] == "security"
    ]
    decoys = [
        (name, int(c["line"]))
        for name, spec in specs.items()
        for c in spec.get("decoys", [])
    ]
    in_scope = [
        f for f in findings if f.file in specs and not f.raw.get("pre_existing")
    ]
    out_of_scope = [f for f in in_scope if security_only and f.category != "security"]
    considered = [f for f in in_scope if f not in out_of_scope]
    match(defects, considered, tolerance, strict, window)

    matched = [d for d in defects if d.matched_by is not None]
    high = [d for d in defects if d.spec["severity"] in ("blocker", "major")]
    sev_pairs = [
        (d.matched_by.severity, d.spec["severity"])
        for d in matched
        if d.matched_by is not None
    ]
    exact = sum(1 for got, want in sev_pairs if got == want)
    near = sum(
        1
        for got, want in sev_pairs
        if got in SEVERITIES
        and abs(SEVERITIES.index(got) - SEVERITIES.index(want)) <= 1
    )
    extras = [f for f in considered if f.matched is None]
    decoy_fp = [
        f
        for f in extras
        if f.severity != "nit"
        and any(f.file == name and abs(f.line - ln) <= tolerance for name, ln in decoys)
    ]
    clean = {name for name, spec in specs.items() if not spec["defects"]}
    control_bad = [
        f for f in considered if f.file in clean and f.severity in ("blocker", "major")
    ]
    rule_pairs = [
        (d.matched_by.raw.get("rule_id"), d.spec["rule_id"])
        for d in matched
        if d.matched_by is not None
        and d.spec.get("rule_id")
        and d.matched_by.raw.get("rule_id")
    ]

    by_tier: dict[str, dict[str, Any]] = {}
    for tier in sorted({str(d.spec.get("tier", "standard")) for d in defects}):
        group = [d for d in defects if str(d.spec.get("tier", "standard")) == tier]
        hit = sum(1 for d in group if d.matched_by is not None)
        by_tier[tier] = {
            "defects": len(group),
            "matched": hit,
            "recall": ratio(hit, len(group)),
        }

    result: dict[str, Any] = {
        "slice": "security-only" if security_only else "full",
        "defects": len(defects),
        "matched": len(matched),
        "recall_all": ratio(len(matched), len(defects)),
        "recall_blocker_major": ratio(
            sum(1 for d in high if d.matched_by is not None), len(high)
        ),
        "recall_by_tier": by_tier,
        "category_mismatches": sum(1 for f in considered if f.matched and f.mismatch),
        "severity_exact": ratio(exact, len(matched), 0.0),
        "severity_within_one": ratio(near, len(matched), 0.0),
        "rule_id_match": ratio(
            sum(1 for a, b in rule_pairs if a == b), len(rule_pairs), 0.0
        )
        if rule_pairs
        else None,
        "findings": len(considered),
        "extras": len(extras),
        "decoy_false_positives": len(decoy_fp),
        "precision_matched_only": ratio(len(matched), len(considered)),
        "control_blocker_major": len(control_bad),
        "out_of_scope_reported": len(out_of_scope),
        "missed": [
            {
                "file": d.file,
                "id": d.spec["id"],
                "line": d.line,
                "severity": d.spec["severity"],
                "tier": d.spec.get("tier", "standard"),
                "title": d.spec["title"],
            }
            for d in defects
            if d.matched_by is None
        ],
        "extra_findings": [
            {k: f.raw.get(k) for k in ("file", "line", "severity", "title", "rule_id")}
            for f in extras
        ],
        "decoy_hits": [
            {k: f.raw.get(k) for k in ("file", "line", "severity", "title")}
            for f in decoy_fp
        ],
    }
    result["meets"] = {
        "recall_blocker_major": result["recall_blocker_major"]
        >= THRESHOLDS["recall_blocker_major"],
        "severity_exact": result["severity_exact"] >= THRESHOLDS["severity_exact"],
        "control_blocker_major": result["control_blocker_major"]
        == THRESHOLDS["control_blocker_major"],
        "out_of_scope_reported": (not security_only) or not out_of_scope,
    }
    return result


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def summary(r: dict[str, Any]) -> str:
    lines = [
        f"slice {r['slice']}: {r['matched']}/{r['defects']} defects found, recall {pct(r['recall_all'])}, "
        f"blocker+major {pct(r['recall_blocker_major'])}",
        "by tier: "
        + ", ".join(
            f"{t} {v['matched']}/{v['defects']}" for t, v in r["recall_by_tier"].items()
        ),
        f"severity exact {pct(r['severity_exact'])}, within one {pct(r['severity_within_one'])}, "
        f"category mismatches {r['category_mismatches']}",
        f"findings {r['findings']}: extras {r['extras']} (decoy false positives {r['decoy_false_positives']}), "
        f"blocker/major in clean files {r['control_blocker_major']}, out of scope {r['out_of_scope_reported']}",
        "meets: "
        + ", ".join(f"{k}={'yes' if v else 'NO'}" for k, v in r["meets"].items()),
    ]
    lines += [
        f"  missed {m['file']}:{m['line']} {m['severity']} {m['tier']}: {m['title'][:70]}"
        for m in r["missed"]
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("expected", type=Path)
    ap.add_argument("findings", type=Path)
    ap.add_argument("--tolerance", type=int, default=2)
    ap.add_argument("--security-only", action="store_true")
    ap.add_argument("--strict-category", action="store_true")
    ap.add_argument(
        "--evidence-window",
        type=int,
        default=EVIDENCE_WINDOW,
        help="max line distance for a match by quoted evidence (0 turns it off)",
    )
    ap.add_argument("--files", nargs="+", help="score only these corpus files")
    ap.add_argument(
        "--names",
        type=Path,
        help="JSON map of the file names the reviewer saw to corpus names",
    )
    ap.add_argument(
        "--summary", action="store_true", help="print a short table instead of JSON"
    )
    args = ap.parse_args()
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    result = score(
        expected,
        load_findings(
            args.findings,
            json.loads(args.names.read_text(encoding="utf-8")) if args.names else None,
        ),
        args.tolerance,
        args.security_only,
        args.strict_category,
        args.files,
        args.evidence_window,
    )
    if args.summary:
        print(summary(result))
    else:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
