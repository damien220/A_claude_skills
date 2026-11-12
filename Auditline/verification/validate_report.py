"""Mechanical final gate for an Auditline report. Standard library only.

    python verification/validate_report.py .auditline/report.json [--md .auditline/report.md]
                                           [--root DIR] [--no-source-check]

Checks the JSON report against tooling/finding.schema.json (a small evaluator for the keywords
that schema uses, so no third-party package is needed), then the rules of SKILL.md title 18:

  * every finding's ``line`` holds the first line of its ``evidence`` (re-read from the file)
  * no duplicate findings (same file, line and rule ID)
  * ``summary`` counts the findings that are not ``pre_existing``; the verdict matches
  * at most 5 model-sourced nits; findings sorted by severity, then file, then line
  * every ``rule_id`` is defined in tooling/tool_map.json
  * with --md: the Markdown report carries the same findings and the same verdict

Exit status 1 when anything fails.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
SEVERITIES = ("blocker", "major", "minor", "nit")
MODEL_NIT_CAP = 5
LANG_PREFIX = {
    ".py": "PY-",
    ".js": "NODE-",
    ".mjs": "NODE-",
    ".cjs": "NODE-",
    ".ts": ("NODE-", "TS-"),
    ".tsx": "TS-",
    ".jsx": "TS-",
}


# -- a small JSON Schema evaluator (draft 2020-12 subset used by finding.schema.json) ----------


def _is_type(value: Any, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "null": value is None,
    }[name]


def check(
    value: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$"
) -> list[str]:
    """Return the schema violations of ``value`` (empty when valid)."""
    if "$ref" in schema:
        node: Any = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        return check(value, node, root, path)
    errs: list[str] = []
    if "type" in schema and not _is_type(value, schema["type"]):
        return [f"{path}: expected {schema['type']}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{path}: shorter than {schema['minLength']}")
        if len(value) > schema.get("maxLength", 10**9):
            errs.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value < schema.get("minimum", value)
    ):
        errs.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                errs += check(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        errs += [
            f"{path}: missing '{k}'"
            for k in schema.get("required", [])
            if k not in value
        ]
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errs += [f"{path}: unexpected '{k}'" for k in value if k not in props]
        for k, sub in props.items():
            if k in value:
                errs += check(value[k], sub, root, f"{path}.{k}")
    for sub in schema.get("allOf", []):
        errs += check(value, sub, root, path)
    if "anyOf" in schema and not any(
        not check(value, s, root, path) for s in schema["anyOf"]
    ):
        errs.append(f"{path}: matches none of the allowed alternatives")
    if (
        "if" in schema
        and not check(value, schema["if"], root, path)
        and "then" in schema
    ):
        errs += check(value, schema["then"], root, path)
    return errs


# -- the final gate ----------------------------------------------------------------------------


def squash(text: str) -> str:
    return " ".join(text.split())


def gate(
    report: dict[str, Any], root: Path, source_check: bool, known_rules: set[str]
) -> list[str]:
    errs: list[str] = []
    findings: list[dict[str, Any]] = report.get("findings", [])
    seen: set[tuple[str, int, str]] = set()
    for i, f in enumerate(findings):
        tag = f"findings[{i}] {f.get('rule_id')} {f.get('file')}:{f.get('line')}"
        key = (f.get("file", ""), f.get("line", 0), f.get("rule_id", ""))
        if key in seen:
            errs.append(f"{tag}: duplicate finding (merge it)")
        seen.add(key)
        if f.get("rule_id") and known_rules and f["rule_id"] not in known_rules:
            errs.append(f"{tag}: rule ID is not defined in tooling/tool_map.json")
        ev_lines = str(f.get("evidence", "")).splitlines()
        if len(ev_lines) > 5:
            errs.append(f"{tag}: evidence is {len(ev_lines)} lines (limit 5)")
        prefix = LANG_PREFIX.get(Path(str(f.get("file", ""))).suffix)
        rid = str(f.get("rule_id", ""))
        if prefix and not rid.startswith(
            ("X-", *([prefix] if isinstance(prefix, str) else prefix))
        ):
            errs.append(f"{tag}: rule prefix does not match the file's language")
        if not source_check or not ev_lines:
            continue
        path = root / str(f.get("file", ""))
        if not path.is_file():
            errs.append(f"{tag}: file not found under {root}")
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        n = int(f.get("line", 0))
        if not 1 <= n <= len(lines):
            errs.append(f"{tag}: line is outside the file ({len(lines)} lines)")
            continue
        first = ev_lines[0]
        if first.startswith("-"):
            continue  # a removed line is not in the new file; the finding anchors on its neighbour
        if squash(first) not in squash(lines[n - 1]) and squash(
            lines[n - 1]
        ) not in squash(first):
            errs.append(
                f"{tag}: evidence does not match line {n}: {lines[n - 1].strip()[:60]!r}"
            )

    counted = [f for f in findings if not f.get("pre_existing", False)]
    want = {s: sum(1 for f in counted if f.get("severity") == s) for s in SEVERITIES}
    if report.get("summary") != want:
        errs.append(
            f"summary {report.get('summary')} does not match the findings {want}"
        )

    model_nits = sum(
        1 for f in counted if f.get("severity") == "nit" and f.get("source") == "model"
    )
    if model_nits > MODEL_NIT_CAP:
        errs.append(f"{model_nits} model nits (cap {MODEL_NIT_CAP})")

    order = [
        (
            SEVERITIES.index(f.get("severity", "nit")),
            f.get("file", ""),
            f.get("line", 0),
        )
        for f in findings
    ]
    if order != sorted(order):
        errs.append("findings are not sorted by severity, then file, then line")

    if source_check:
        errs.extend(
            f"question {q.get('file')}:{q.get('line')}: file not found"
            for q in report.get("questions", [])
            if not (root / str(q.get("file", ""))).is_file()
        )
    return errs


def check_markdown(report: dict[str, Any], md: str) -> list[str]:
    errs: list[str] = []
    verdict = str(report.get("verdict", ""))
    if verdict.lower() not in md.lower():
        errs.append(f"Markdown does not state the verdict {verdict!r}")
    for f in report.get("findings", []):
        if f.get("source") != "model" and f.get("severity") == "nit":
            continue  # linter nits collapse to a count in the Markdown
        loc = f"{f.get('file')}:{f.get('line')}"
        if loc not in md or str(f.get("rule_id")) not in md:
            errs.append(f"Markdown lacks {f.get('rule_id')} at {loc}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("report", type=Path, help="the JSON report")
    ap.add_argument("--md", type=Path, help="the Markdown report to compare")
    ap.add_argument(
        "--root", type=Path, default=Path.cwd(), help="project root for source checks"
    )
    ap.add_argument(
        "--no-source-check", action="store_true", help="skip re-reading the files"
    )
    ap.add_argument(
        "--schema", type=Path, default=SKILL_ROOT / "tooling" / "finding.schema.json"
    )
    args = ap.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    errs = check(report, schema, schema)
    if not errs:  # the semantic gate assumes a well-formed report
        tool_map = SKILL_ROOT / "tooling" / "tool_map.json"
        known = (
            set(json.loads(tool_map.read_text(encoding="utf-8"))["rules"])
            if tool_map.exists()
            else set()
        )
        errs += gate(report, args.root.resolve(), not args.no_source_check, known)
        if args.md:
            errs += check_markdown(report, args.md.read_text(encoding="utf-8"))
    for e in errs:
        print(f"ERROR: {e}")
    n = len(report.get("findings", [])) if isinstance(report, dict) else 0
    print(f"{n} findings checked, {len(errs)} errors")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
