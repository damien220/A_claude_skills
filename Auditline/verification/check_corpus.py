"""Validate the seeded-defect corpus: ground truth against the files, and the P6 coverage floor.

    python verification/check_corpus.py [--root DIR] [--node PATH]

For every language directory (python, node, typescript) this checks that

  * every source file is listed in ``expected.json`` and every listed file exists and parses
  * each defect has the required fields, a unique ID and a unique anchor line
  * ``evidence`` equals the stripped text of line ``line`` (so the ground truth cannot drift)
  * decoys do not sit on a defect line
  * the corpus meets the floor from plan.md section 9, P6: at least 15 defects, at least 5 of
    them hard-tier, every severity present, at least 3 security defects (the security-only
    slice), at least 2 clean controls, and a written rationale for every defect

Standard library only. JavaScript needs ``node`` on PATH and TypeScript needs the compiler
(``--tsc-module``, a path to the ``typescript`` package); a check whose tool is missing is skipped
and said so.
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

SEVERITIES = {"blocker", "major", "minor", "nit"}
CATEGORIES = {
    "security",
    "correctness",
    "error-handling",
    "performance",
    "tests",
    "maintainability",
    "diff-hygiene",
}
TIERS = {"standard", "hard"}
REQUIRED = ("id", "line", "category", "severity", "title", "evidence", "rationale")
SOURCE_EXT = {"python": ".py", "node": ".mjs", "typescript": ".tsx"}
FLOOR = {"defects": 15, "hard": 5, "security": 3, "clean": 2}


def parse_check(
    lang: str, path: Path, node: str | None, tsc_module: str | None
) -> str | None:
    """Return an error string, or None when the file parses (or the check is skipped)."""
    if lang == "python":
        try:
            ast.parse(path.read_text(encoding="utf-8"), str(path))
        except SyntaxError as exc:
            return f"syntax error line {exc.lineno}: {exc.msg}"
    elif lang == "node" and node:
        done = subprocess.run(  # noqa: S603 - node from PATH, file is part of the corpus
            [node, "--check", str(path)], capture_output=True, text=True, check=False
        )
        if done.returncode:
            return (
                done.stderr.strip().splitlines()[0]
                if done.stderr
                else "node --check failed"
            )
    elif lang == "typescript" and node and tsc_module:
        script = (
            "const ts=require(process.argv[1]);const fs=require('fs');const f=process.argv[2];"
            "const sf=ts.createSourceFile(f,fs.readFileSync(f,'utf8'),ts.ScriptTarget.ES2022,true,"
            "f.endsWith('x')?ts.ScriptKind.TSX:ts.ScriptKind.TS);"
            "const d=sf.parseDiagnostics;if(d.length){console.log(d.length+' parse errors, first at '"
            "+(sf.getLineAndCharacterOfPosition(d[0].start).line+1));process.exit(1)}"
        )
        done = subprocess.run(  # noqa: S603 - node from PATH, script is a constant
            [node, "-e", script, tsc_module, str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode:
            return done.stdout.strip() or done.stderr.strip()
    return None


def check_language(
    lang: str, root: Path, node: str | None, tsc_module: str | None
) -> tuple[list[str], dict[str, int]]:
    errs: list[str] = []
    base = root / lang
    exp_path = base / "expected.json"
    expected = json.loads(exp_path.read_text(encoding="utf-8"))["files"]
    ext = SOURCE_EXT[lang]
    on_disk = {p.name for p in base.glob(f"sample_*{ext}")}
    errs.extend(
        f"{lang}/{n} is not in expected.json" for n in sorted(on_disk - set(expected))
    )
    counts = {"defects": 0, "hard": 0, "security": 0, "clean": 0}
    severities: set[str] = set()
    for name, spec in expected.items():
        path = base / name
        if not path.is_file():
            errs.append(f"{lang}/{name} is listed but missing")
            continue
        problem = parse_check(lang, path, node, tsc_module)
        if problem:
            errs.append(f"{lang}/{name}: {problem}")
        lines = path.read_text(encoding="utf-8").splitlines()
        defects = spec.get("defects", [])
        if not defects:
            counts["clean"] += 1
        ids: set[str] = set()
        anchors: set[int] = set()
        for d in defects:
            tag = f"{lang}/{name} {d.get('id')}"
            errs.extend(
                f"{tag}: missing {f}" for f in REQUIRED if not str(d.get(f, "")).strip()
            )
            if d.get("id") in ids:
                errs.append(f"{tag}: duplicate ID")
            ids.add(d.get("id", ""))
            if d.get("severity") not in SEVERITIES:
                errs.append(f"{tag}: bad severity {d.get('severity')!r}")
            if d.get("category") not in CATEGORIES:
                errs.append(f"{tag}: bad category {d.get('category')!r}")
            if d.get("tier", "standard") not in TIERS:
                errs.append(f"{tag}: bad tier {d.get('tier')!r}")
            n = int(d.get("line", 0))
            if n in anchors:
                errs.append(f"{tag}: anchor line {n} used twice")
            anchors.add(n)
            if not 1 <= n <= len(lines):
                errs.append(f"{tag}: line {n} is outside the file ({len(lines)} lines)")
            elif lines[n - 1].strip() != str(d.get("evidence", "")).strip():
                errs.append(
                    f"{tag}: evidence differs from line {n}: {lines[n - 1].strip()[:60]!r}"
                )
            span = d.get("span")
            if span is not None and not (
                isinstance(span, list)
                and len(span) == 2
                and all(isinstance(x, int) for x in span)
                and 1 <= span[0] <= n <= span[1] <= len(lines)
            ):
                errs.append(
                    f"{tag}: span {span!r} must be [first, last] around line {n}"
                )
            counts["defects"] += 1
            counts["hard"] += d.get("tier") == "hard"
            counts["security"] += d.get("category") == "security"
            severities.add(d.get("severity", ""))
        for c in spec.get("decoys", []):
            n = int(c.get("line", 0))
            tag = f"{lang}/{name} decoy@{n}"
            if n in anchors:
                errs.append(f"{tag}: sits on a defect line")
            if not 1 <= n <= len(lines):
                errs.append(f"{tag}: line outside the file")
            elif c.get("evidence") and lines[n - 1].strip() != c["evidence"].strip():
                errs.append(f"{tag}: evidence differs from the line")
    errs.extend(
        f"{lang}: {counts[k]} {k} (floor {n})"
        for k, n in FLOOR.items()
        if counts[k] < n
    )
    errs.extend(f"{lang}: no {sev} defect" for sev in sorted(SEVERITIES - severities))
    return errs, counts


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--node", default=shutil.which("node"))
    ap.add_argument(
        "--tsc-module", help="path to the typescript package, for .tsx parsing"
    )
    args = ap.parse_args()
    total = 0
    for lang in SOURCE_EXT:
        errs, counts = check_language(lang, args.root, args.node, args.tsc_module)
        print(
            f"{lang}: {counts['defects']} defects ({counts['hard']} hard, {counts['security']} security), {counts['clean']} clean controls"
        )
        for e in errs:
            print(f"  ERROR: {e}")
        total += len(errs)
    if not args.tsc_module:
        print("note: .tsx files were not parsed (no --tsc-module)")
    print(f"{total} errors")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
