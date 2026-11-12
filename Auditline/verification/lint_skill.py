"""Structural lint for the Auditline skill. Standard library only.

    python verification/lint_skill.py [--root DIR] [--node PATH] [--strict]

Checks (plan.md section 10):
  * SKILL.md frontmatter (kebab-case name, description length), line budget, routing
  * every ref is named in SKILL.md and every named ref exists
  * each ref: H1, Sources line, TOC over 100 lines, a WRONG/CORRECT pair, a citation
  * each rule: Detect, Default severity, Why, WRONG, CORRECT, Fix, Cite, Tool code
  * rule IDs: well formed, unique, and every ID named in prose resolves to a heading
  * rule maps in the topic refs list the same concepts as their headings
  * tooling/*-review-checklist.md lists exactly the rules of its language (one to one)
  * provenance comments in refs/lang/ are well formed
  * shipped files carry no sibling-directory references
  * Python and JavaScript code blocks parse (JavaScript needs ``node`` on PATH)

Exit status is 1 when any error is found; warnings do not fail unless --strict.
"""

from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ID_RE = re.compile(r"^(PY|NODE|TS|X)-[A-Z]+-[0-9]{2}$")
ID_FIND = re.compile(r"\b(?:PY|NODE|TS|X)(?:/(?:PY|NODE|TS))*-[A-Z]+-\d\d\b")
FIELDS = (
    "**Detect:**",
    "**Default severity:**",
    "**Why:**",
    "WRONG",
    "CORRECT",
    "**Fix:**",
    "**Cite:**",
    "**Tool code:**",
)
CORE_REFS = {"review-process.md", "severity-and-output-format.md"}
TOPIC_REFS = (
    "correctness.md",
    "performance.md",
    "error-handling.md",
    "tests.md",
    "maintainability.md",
    "diff-hygiene.md",
)
LANG_CHECKLISTS = {
    "PY": ("python-review-checklist.md", "python-checklist.md"),
    "NODE": ("node-review-checklist.md", "node-checklist.md"),
    "TS": ("typescript-review-checklist.md", "typescript-react-checklist.md"),
}
PROVENANCE = re.compile(
    r"<!-- provenance: (CodeWriter/(?:python|node|typescript)/refs/[\w.-]+\.md) @ ([0-9a-f]{40}) -->"
)
SIBLING = re.compile(
    r"Dev_Agents|Dev_util_prj|CodeWriter/|\.\./(?:plan|planned|CLAUDE|README|CodeWriter|Gantt|ProdReel)"
)
RESERVED = ("anthropic", "claude")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


@dataclass
class Rule:
    ids: list[str]
    heading: str
    body: str
    path: Path


def expand_ids(text: str) -> list[str]:
    """Expand ``PY/NODE-SEC-04`` shorthand into full IDs."""
    out: list[str] = []
    for token in ID_FIND.findall(text):
        head, _, tail = token.rpartition("-")
        cat_head, _, cat = head.rpartition("-")
        out.extend(f"{p}-{cat}-{tail}" for p in cat_head.split("/"))
    return out


def split_rules(path: Path) -> list[Rule]:
    """Split a ref into rules at ``### `` headings that sit outside code fences."""
    sections: list[list[str]] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            sections.append([])  # an H2 closes the previous rule
            continue
        if not in_fence and line.startswith("### "):
            sections.append([line])
        elif sections:
            sections[-1].append(line)
    rules: list[Rule] = []
    for sec in sections:
        if not sec or not sec[0].startswith("### "):
            continue
        heading = sec[0][4:]
        ids = expand_ids(heading)
        if ids:
            rules.append(Rule(ids, heading, "\n".join(sec[1:]), path))
    return rules


def check_skill_md(root: Path, rep: Report) -> set[str]:
    skill = root / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) > 500:
        rep.error(f"SKILL.md has {len(lines)} lines (limit 500)")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        rep.error("SKILL.md has no frontmatter")
        return set()
    front = m.group(1)
    name = re.search(r"^name:\s*(\S+)", front, re.M)
    if not name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name.group(1)):
        rep.error("SKILL.md name is missing or not kebab-case")
    elif any(w in name.group(1) for w in RESERVED):
        rep.error("SKILL.md name contains a reserved word")
    desc = re.search(r"^description:\s*(.*?)(?=^\w+:|\Z)", front, re.M | re.S)
    if not desc:
        rep.error("SKILL.md has no description")
    else:
        joined = " ".join(desc.group(1).split())
        if len(joined) > 1024:
            rep.error(f"description is {len(joined)} chars (limit 1024)")
        if "does not write" not in joined and "do not write" not in joined:
            rep.warn("description should say the skill reviews and does not write")
    return set(re.findall(r"refs/[\w/.-]+\.md", text))


def check_routing(root: Path, named: set[str], rep: Report) -> None:
    on_disk = {p.relative_to(root).as_posix() for p in (root / "refs").rglob("*.md")}
    for ref in sorted(named - on_disk):
        rep.error(f"SKILL.md names {ref}, which does not exist")
    for ref in sorted(on_disk - named):
        rep.error(f"{ref} exists but SKILL.md never names it")


def check_ref_shape(path: Path, root: Path, rep: Report) -> None:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        rep.error(f"{rel}: first line is not an H1")
    if not any(ln.startswith("Sources:") for ln in lines[:8]):
        rep.error(f"{rel}: no 'Sources:' line near the top")
    if len(lines) > 100 and "## Contents" not in text:
        rep.error(f"{rel}: {len(lines)} lines and no '## Contents'")
    if "WRONG" not in text or "CORRECT" not in text:
        rep.error(f"{rel}: no WRONG/CORRECT pair")
    if not re.search(r"\*\*Cite:\*\*|^Cite:", text, re.M):
        rep.error(f"{rel}: no citation")


def check_rules(refs: list[Path], root: Path, rep: Report) -> dict[str, Path]:
    seen: dict[str, Path] = {}
    for path in refs:
        if path.name in CORE_REFS and path.name != "severity-and-output-format.md":
            continue
        rel = path.relative_to(root).as_posix()
        for rule in split_rules(path):
            for rid in rule.ids:
                if not ID_RE.match(rid):
                    rep.error(f"{rel}: malformed ID {rid}")
                if rid in seen:
                    rep.error(f"{rel}: duplicate ID {rid} (also in {seen[rid].name})")
                seen[rid] = path
            first = rule.ids[0]
            if path.name == "severity-and-output-format.md" and "-SEV-" not in first:
                continue
            table_form = "**Detect / WRONG" in rule.body
            for fld in FIELDS:
                if table_form and fld in (
                    "**Detect:**",
                    "WRONG",
                    "CORRECT",
                    "**Cite:**",
                ):
                    continue
                if fld not in rule.body:
                    rep.error(f"{rel}: {first} is missing {fld}")
            if table_form and "| Cite |" not in rule.body:
                rep.error(f"{rel}: {first} is table-form with no Cite column")
            if not table_form and "```" not in rule.body:
                rep.error(f"{rel}: {first} has no code")
    return seen


def check_references(
    refs: list[Path], known: set[str], root: Path, rep: Report
) -> None:
    for path in refs:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for rid in set(expand_ids(text)):
            if rid not in known:
                rep.error(f"{rel}: refers to undefined rule {rid}")


def check_rule_maps(root: Path, rep: Report) -> None:
    for name in TOPIC_REFS:
        path = root / "refs" / name
        text = path.read_text(encoding="utf-8")
        m = re.search(r"## 2\. Rule map\n(.*?)\n## ", text, re.S)
        if not m:
            rep.error(f"refs/{name}: no '## 2. Rule map'")
            continue

        def concept(i: str) -> str:
            return re.sub(r"^(?:PY|NODE|TS|X)-", "", i)

        mapped = {
            concept(c) if re.match(r"(PY|NODE|TS|X)-", c) else c
            for c in re.findall(
                r"^\| ((?:(?:PY|NODE|TS|X)-)?[A-Z]+-\d\d) \|", m.group(1), re.M
            )
        }
        headed = {concept(i) for r in split_rules(path) for i in r.ids}
        if mapped != headed:
            rep.error(
                f"refs/{name}: rule map {sorted(mapped ^ headed)} differs from the headings"
            )


def check_tooling_checklists(root: Path, known: set[str], rep: Report) -> None:
    for prefix, (fname, _) in LANG_CHECKLISTS.items():
        path = root / "tooling" / fname
        if not path.exists():
            rep.error(f"tooling/{fname} is missing")
            continue
        listed = re.findall(
            r"^- \[ \] \*\*((?:PY|NODE|TS|X)-[A-Z]+-\d\d)\*\*", path.read_text(), re.M
        )
        dup = {i for i in listed if listed.count(i) > 1}
        if dup:
            rep.error(f"tooling/{fname}: duplicate entries {sorted(dup)}")
        want = {
            i for i in known if i.startswith((f"{prefix}-", "X-")) and "-SEV-" not in i
        }
        for missing in sorted(want - set(listed)):
            rep.error(f"tooling/{fname}: missing {missing}")
        for extra in sorted(set(listed) - want):
            rep.error(f"tooling/{fname}: lists {extra}, which no ref defines")


def check_provenance(root: Path, rep: Report) -> None:
    for prefix, (_, lang_file) in LANG_CHECKLISTS.items():
        path = root / "refs" / "lang" / lang_file
        if not path.exists():
            rep.error(f"refs/lang/{lang_file} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        marks = PROVENANCE.findall(text)
        if not marks:
            rep.error(f"refs/lang/{lang_file}: no provenance comments")
        if "@ SHA" in text:
            rep.error(f"refs/lang/{lang_file}: unfilled provenance placeholder")
        lang = {"PY": "python", "NODE": "node", "TS": "typescript"}[prefix]
        for src, _sha in marks:
            if f"CodeWriter/{lang}/" not in src:
                rep.error(
                    f"refs/lang/{lang_file}: provenance {src} is for another language"
                )
        if len({s for s, _ in marks}) != len(marks):
            rep.error(f"refs/lang/{lang_file}: a source is mapped twice")


def check_siblings(root: Path, rep: Report) -> None:
    shipped = [
        root / "SKILL.md",
        *(root / "refs").rglob("*.md"),
        *(root / "tooling").rglob("*.md"),
    ]
    readme = root / "README.md"
    if readme.exists():
        shipped.append(readme)
    for path in shipped:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PROVENANCE.search(line):
                continue
            if SIBLING.search(line):
                rep.error(f"{path.relative_to(root)}:{n}: sibling-directory reference")


def code_blocks(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    out = []
    for lang, body in re.findall(r"```(\w+)\n(.*?)```", text, re.S):
        dedented = "\n".join(
            ln[2:] if ln.startswith("  ") else ln for ln in body.splitlines()
        )
        out.append((lang, dedented))
    return out


def parses_python(code: str) -> bool:
    first = code.lstrip().split(None, 1)[0] if code.strip() else ""
    if first.rstrip(":") in {"except", "finally", "elif", "else"}:
        code = "try:\n    pass\n" + code  # a clause shown without its opener
    if code.rstrip().endswith(":"):
        code += "\n    pass"
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        pass
    if re.match(r"\s*@", code) and "def " not in code:
        code += "\ndef _f(): pass"
    for wrapper in ("{}", "async def __w():\n{}"):
        src = (
            code
            if wrapper == "{}"
            else wrapper.format("\n".join("    " + ln for ln in code.splitlines()))
        )
        try:
            ast.parse(src)
            return True
        except SyntaxError:
            continue
    return False


def node_accepts(node: str, path: Path) -> bool:
    """True when ``node --check`` accepts the file."""
    done = subprocess.run(  # noqa: S603 - node path from PATH or --node, file is ours
        [node, "--check", str(path)], capture_output=True, check=False
    )
    return done.returncode == 0


def parses_js(code: str, node: str, tmp: Path, n: int) -> bool:
    if code.lstrip().startswith("}"):
        code = "try {\n" + code  # a clause shown without its opener
    if code.rstrip().endswith("{"):
        code += "\n}"  # an opener shown without its body
    raw = tmp / f"r{n}.mjs"
    raw.write_text(code, encoding="utf-8")
    if node_accepts(node, raw):
        return True
    imports = [ln for ln in code.splitlines() if re.match(r"\s*import\s", ln)]
    rest = [ln for ln in code.splitlines() if ln not in imports]
    wrapped = tmp / f"w{n}.mjs"
    wrapped.write_text(
        "\n".join(imports)
        + "\nasync function __w(req, reply, res, app) {\n"
        + "\n".join(rest)
        + "\n}\n"
    )
    return node_accepts(node, wrapped)


def check_code(refs: list[Path], root: Path, node: str | None, rep: Report) -> None:
    tmp = Path(tempfile.mkdtemp())
    n = 0
    for path in refs:
        rel = path.relative_to(root).as_posix()
        for lang, code in code_blocks(path):
            if "…" in code:
                continue
            n += 1
            if lang == "python" and not parses_python(code):
                rep.warn(
                    f"{rel}: python block does not parse: {code.splitlines()[0][:60]!r}"
                )
            elif lang == "js" and node and not parses_js(code, node, tmp, n):
                rep.warn(
                    f"{rel}: js block does not parse: {code.splitlines()[0][:60]!r}"
                )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument(
        "--node",
        default=shutil.which("node"),
        help="node executable for JS syntax checks",
    )
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()
    root: Path = args.root.resolve()
    rep = Report()

    named = check_skill_md(root, rep)
    check_routing(root, named, rep)
    refs = sorted((root / "refs").rglob("*.md"))
    for ref in refs:
        check_ref_shape(ref, root, rep)
    seen = check_rules(refs, root, rep)
    check_references(refs, set(seen), root, rep)
    check_rule_maps(root, rep)
    check_tooling_checklists(root, set(seen), rep)
    check_provenance(root, rep)
    check_siblings(root, rep)
    check_code(refs, root, args.node, rep)

    for w in rep.warnings:
        print(f"warning: {w}")
    for e in rep.errors:
        print(f"ERROR: {e}")
    print(
        f"{len(refs)} refs, {len(seen)} rule IDs, "
        f"{len(rep.errors)} errors, {len(rep.warnings)} warnings"
    )
    failed = bool(rep.errors) or (args.strict and bool(rep.warnings))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
