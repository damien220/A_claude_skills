"""Score evaluation runs and compare the skill with the no-skill baseline.

Maintainer tool, not shipped. Standard library only.

    python maintainer/eval_report.py --eval DIR [--tasks DIR] [--json OUT]

DIR holds ``runs/<lang>_<model>_<skill|plain>.json`` (the reviewers' reports), ``truth/`` (the
ground truth and file-name maps written by prepare_eval.py) and ``skillbundle/``. With --tasks (the
directory of subagent transcripts) it also reports, per run, tokens, the reference files the
reviewer read, whether each seeded defect's reference was read (routing), and any read of the
ground truth (a leak invalidates the run).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LANGS = ("python", "node", "typescript")
MODELS = ("haiku", "sonnet", "opus")
# ground-truth paths only; applied to the arguments of read-like tools, never to Write contents
LEAK = re.compile(
    r"(?:^|[/\s\"'])(?:truth|baseline)(?:/|_names|\b[\"']|$)|expected(?:\.json|_new)",
    re.I,
)
READ_TOOLS = ("Read", "Glob", "Grep", "Bash", "NotebookRead")
READ_ARGS = ("file_path", "path", "pattern", "command", "glob")


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SC = load("score", ROOT / "verification" / "score.py")
VR = load("validate_report", ROOT / "verification" / "validate_report.py")


def read_transcript(path: Path) -> dict[str, Any]:
    """Tokens, tool calls, skill files read and suspicious reads from a subagent transcript."""
    refs: set[str] = set()
    leaks: list[str] = []
    tokens = calls = 0
    key = ""
    stamps: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if d.get("timestamp"):
            stamps.append(d["timestamp"])
        msg = d.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if d.get("type") == "user" and isinstance(content, str) and not key:
            m = re.search(r"prompt_(\w+?_\w+?_(?:skill|plain))\.txt", content)
            key = m.group(1) if m else ""
        usage = msg.get("usage")
        if d.get("type") == "assistant" and isinstance(usage, dict):
            tokens += sum(
                int(usage.get(k, 0) or 0) for k in ("input_tokens", "output_tokens")
            )
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") != "tool_use":
                continue
            calls += 1
            args = json.dumps(block.get("input", {}))
            # absolute, relative (after a cd into the skill) and `./` forms all count
            for m2 in re.finditer(
                r"(?:^|[/\s\"'=])((?:refs|tooling)/[\w/.-]+|SKILL\.md)", args
            ):
                refs.add(m2.group(1))
            if block.get("name") in READ_TOOLS:
                inp = block.get("input", {})
                probe = " ".join(str(inp.get(k, "")) for k in READ_ARGS)
                if LEAK.search(probe) and "prompt_" not in probe:
                    leaks.append(f"{block.get('name')}: {probe[:120]}")
    return {
        "key": key,
        "tokens": tokens,
        "calls": calls,
        "refs": sorted(refs),
        "leaks": leaks,
        "stamps": stamps,
    }


def run_metrics(
    expected: dict[str, Any],
    names: dict[str, str],
    report: Path,
    tool_map: dict[str, Any],
    transcript: dict[str, Any] | None,
    skill: bool,
    inputs: Path,
) -> dict[str, Any]:
    findings = SC.load_findings(report, names)
    res: dict[str, Any] = SC.score(expected, findings)
    sec: dict[str, Any] = SC.score(expected, findings, security_only=True)
    res["security_recall"] = sec["recall_all"]
    raw = json.loads(report.read_text(encoding="utf-8"))
    flist = raw["findings"] if isinstance(raw, dict) else raw
    res["n_findings"] = len(flist)
    res["with_rule_id"] = sum(1 for f in flist if f.get("rule_id")) / max(1, len(flist))
    res["with_cite"] = sum(1 for f in flist if str(f.get("cite", "")).strip()) / max(
        1, len(flist)
    )
    if skill:
        schema = json.loads(
            (ROOT / "tooling" / "finding.schema.json").read_text(encoding="utf-8")
        )
        errs = VR.check(raw, schema, schema)
        if not errs:
            errs += VR.gate(raw, inputs, True, set(tool_map["rules"]))
        res["report_errors"] = errs
        res["report_valid"] = not errs
    if transcript is not None:
        read = set(transcript["refs"])
        rules = tool_map["rules"]
        defects = [
            d
            for f in expected["files"].values()
            for d in f["defects"]
            if d.get("rule_id")
        ]
        needed = {
            d["rule_id"]: rules[d["rule_id"]]["ref"]
            for d in defects
            if d["rule_id"] in rules
        }
        hit = {
            k
            for k, ref in needed.items()
            if ref in read or Path(ref).name in {Path(r).name for r in read}
        }
        res["routing_ref_read"] = len(hit) / max(1, len(needed))
        res["refs_read"] = transcript["refs"]
        res["tokens"] = transcript["tokens"]
        res["tool_calls"] = transcript["calls"]
        res["leaks"] = transcript["leaks"]
        res["missed_unrouted"] = sum(
            1
            for m in res["missed"]
            for d in defects
            if d["rule_id"] in needed
            and d["line"] == m["line"]
            and needed[d["rule_id"]] not in read
        )
    return res


def pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def table(rows: list[dict[str, Any]]) -> str:
    head = (
        "| lang | model | cond | recall | b+m | hard | sec | sev exact | findings | extras | decoy FP | clean b/m "
        "| rule id | cite | report ok | tokens | refs read |"
    )
    lines = [head, "|" + "---|" * 17]
    for r in rows:
        hard = r["recall_by_tier"].get("hard", {}).get("recall")
        lines.append(
            f"| {r['lang']} | {r['model']} | {r['cond']} | {pct(r['recall_all'])} | {pct(r['recall_blocker_major'])} "
            f"| {pct(hard)} | {pct(r['security_recall'])} | {pct(r['severity_exact'])} | {r['n_findings']} "
            f"| {r['extras']} | {r['decoy_false_positives']} | {r['control_blocker_major']} "
            f"| {pct(r['with_rule_id'])} | {pct(r['with_cite'])} "
            f"| {'-' if 'report_valid' not in r else ('yes' if r['report_valid'] else 'NO')} "
            f"| {r.get('tokens', '-')} | {len(r.get('refs_read', [])) or '-'} |"
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--eval", type=Path, required=True)
    ap.add_argument(
        "--tasks", type=Path, help="directory of subagent transcripts (*.output)"
    )
    ap.add_argument("--json", type=Path, help="write the raw metrics here")
    args = ap.parse_args()
    ev: Path = args.eval
    tool_map = json.loads(
        (ROOT / "tooling" / "tool_map.json").read_text(encoding="utf-8")
    )
    transcripts: dict[str, dict[str, Any]] = {}
    if args.tasks:
        for p in args.tasks.glob("*.output"):
            try:
                t = read_transcript(p)
            except json.JSONDecodeError:
                continue  # a background shell task's output, not a subagent transcript
            if t["key"]:
                transcripts[t["key"]] = t
    rows: list[dict[str, Any]] = []
    for lang in LANGS:
        expected = json.loads(
            (ev / "truth" / f"{lang}.json").read_text(encoding="utf-8")
        )
        names = json.loads(
            (ev / "truth" / f"{lang}_names.json").read_text(encoding="utf-8")
        )
        back = dict(names)
        for model in MODELS:
            for cond in ("skill", "plain"):
                rep = ev / "runs" / f"{lang}_{model}_{cond}.json"
                if not rep.exists():
                    continue
                try:
                    m = run_metrics(
                        expected,
                        back,
                        rep,
                        tool_map,
                        transcripts.get(f"{lang}_{model}_{cond}"),
                        cond == "skill",
                        ev / "skillbundle" / "inputs" / lang,
                    )
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    print(f"{rep.name}: unreadable ({exc})", file=sys.stderr)
                    continue
                rows.append({"lang": lang, "model": model, "cond": cond, **m})
    print(table(rows))
    for r in rows:
        if r.get("leaks"):
            print(f"\nLEAK in {r['lang']}_{r['model']}_{r['cond']}: {r['leaks'][:3]}")
        if r.get("report_errors"):
            print(f"\nreport errors {r['lang']}_{r['model']}: {r['report_errors'][:3]}")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
