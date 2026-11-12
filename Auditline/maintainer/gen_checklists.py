"""Generate tooling/<lang>-review-checklist.md from the rule headings in refs/.

Maintainer tool, not shipped. Run from anywhere:

    python maintainer/gen_checklists.py          # write the three files
    python maintainer/gen_checklists.py --check  # exit 1 if a file is out of date

Every rule in refs/ (security, the six topic refs, the language checklists) appears once in the
checklist of each language it names, so the checklists are one-to-one with the refs by
construction. X-<CAT>-NN rules appear in all three.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "refs"
OUT = ROOT / "tooling"
FALLBACK = OUT / "fallback"
DEV_SKILLS = ROOT.parent

ID_RE = re.compile(r"\b(?:PY|NODE|TS|X)-[A-Z]+-\d\d\b")
LEVELS = ("blocker", "major", "minor", "nit")
TIER = ("SEC", "COR", "ACC", "ERR", "PERF", "TEST", "MAINT", "OPS", "DIFF")
TIER_TITLE = {
    "SEC": "Security",
    "COR": "Correctness",
    "ACC": "Accessibility (triaged with correctness)",
    "ERR": "Error handling",
    "PERF": "Performance",
    "TEST": "Tests",
    "MAINT": "Maintainability",
    "OPS": "Deployment (triaged with maintainability)",
    "DIFF": "Diff hygiene",
}
LANGS = {
    "PY": ("python", "Python", "python-checklist.md", "[ruff] [mypy]"),
    "NODE": ("node", "Node.js", "node-checklist.md", "[eslint] [tsc]"),
    "TS": (
        "typescript",
        "TypeScript/React",
        "typescript-react-checklist.md",
        "[eslint] [tsc]",
    ),
}
REF_FILES = [
    "security.md",
    "correctness.md",
    "performance.md",
    "error-handling.md",
    "tests.md",
    "maintainability.md",
    "diff-hygiene.md",
]


TOOL_GROUP = re.compile(r"\[([A-Za-z@/-]+):\s*([^\]]+)\]")
PY_TOOLS = {"ruff", "mypy", "pylint"}
JS_TOOLS = {
    "eslint",
    "typescript-eslint",
    "tsc",
    "jsx-a11y",
    "eslint-plugin-react",
    "eslint-plugin-react-hooks",
}


def tools_for(prefix: str, text: str) -> str:
    """Keep only the bracketed tool groups that belong to the checklist's language."""
    keep = PY_TOOLS if prefix == "PY" else JS_TOOLS
    groups = [
        f"[{n}: {c.strip()}]"
        for n, c in TOOL_GROUP.findall(text)
        if n in keep or n == "gitleaks"
    ]
    return " ".join(groups)


# Tool codes that point at more than one rule. The first listed rule is the default; the
# model changes it when the consequence differs (for example T201 logging a secret is SEC-23).
PRIMARY: dict[tuple[str, str], str] = {
    ("eslint", "@typescript-eslint/ban-ts-comment"): "MAINT-08",
    ("eslint", "@typescript-eslint/no-floating-promises"): "COR-10",
    ("eslint", "@typescript-eslint/no-misused-promises"): "COR-10",
    ("eslint", "@typescript-eslint/no-non-null-assertion"): "MAINT-08",
    ("eslint", "no-console"): "DIFF-01",
    ("eslint", "testing-library/prefer-find-by"): "TEST-05",
    ("ruff", "BLE001"): "ERR-02",
    ("ruff", "E722"): "ERR-02",
    ("ruff", "S110"): "ERR-01",
    ("ruff", "S112"): "ERR-01",
    ("ruff", "D417"): "MAINT-09",
    ("ruff", "PGH003"): "MAINT-08",
    ("ruff", "RUF006"): "COR-10",
    ("ruff", "S501"): "SEC-12",
    ("ruff", "T201"): "DIFF-01",
}
# Codes a tool raises on correct code too: reported to the model, never as a finding.
ADVISORY: dict[str, list[str]] = {"ruff": ["PLC0415"]}
TOOL_STOP = {"none", "only", "true", "props:", "model", "finding", "tool", "tools"}
PY_ONLY_TOOLS = {"ruff", "mypy", "pylint"}
# Mapped to rules, but too noisy for the fallback (they fire on correct code or are pure style).
# A project that configures them itself still gets its results mapped.
FALLBACK_SKIP = {
    "ruff": {
        "PLR2004",
        "PLR0912",
        "PLR0913",
        "PLR0915",
        "C901",
        "FBT001",
        "FBT002",
        "ARG001",
        "I001",
        "N801",
        "N802",
        "N806",
    },
    "eslint": {
        "no-magic-numbers",
        "sort-imports",
        "max-lines-per-function",
        "max-depth",
        "max-params",
        "complexity",
        "no-undef",
        "no-warning-comments",
    },
}
CODE_SHAPE = {
    "ruff": re.compile(r"[A-Z]{1,5}\d{3}"),
    "mypy": re.compile(r"[a-z][a-z-]+"),
    "tsc": re.compile(r"TS\d{4,5}"),
}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    levels: tuple[str, ...]
    tools: str
    ref: str  # path relative to the skill root, e.g. refs/correctness.md
    cite: str = ""
    fix: str = ""

    @property
    def category(self) -> str:
        return self.rule_id.split("-")[1]


@dataclass
class Collected:
    rules: list[Rule] = field(default_factory=list)


def _levels(text: str) -> tuple[str, ...]:
    found = [lvl for lvl in LEVELS if re.search(rf"\b{lvl}\b", text)]
    return tuple(found)


def parse_ref(path: Path) -> list[Rule]:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(ROOT).as_posix()
    rules: list[Rule] = []
    for part in re.split(r"^### ", text, flags=re.M)[1:]:
        heading, _, body = part.partition("\n")
        body = re.split(r"^## ", body, maxsplit=1, flags=re.M)[0]
        ids = ID_RE.findall(heading)
        if not ids:
            continue
        title = heading.split("—", 1)[-1].strip() if "—" in heading else heading.strip()
        sev = re.search(r"\*\*Default severity:\*\*(.*?)(?=\n- \*\*|\Z)", body, re.S)
        tools = re.search(r"\*\*Tool code:\*\*(.*?)(?=\n\n|\n- |\n###|\Z)", body, re.S)
        tool_text = " ".join(tools.group(1).split()) if tools else ""
        cite_m = re.search(r"\*\*Cite:\*\*(.*?)(?=\n- \*\*|\Z)", body, re.S)
        fix_m = re.search(r"\*\*Fix:\*\*(.*?)(?=\n- \*\*|\n- WRONG|\Z)", body, re.S)
        cite = " ".join(cite_m.group(1).split()).split(";")[0:2] if cite_m else []
        fix = " ".join(fix_m.group(1).split()) if fix_m else ""
        levels = _levels(sev.group(1)) if sev else ()
        rules.extend(
            Rule(
                rid,
                title,
                levels,
                tool_text,
                rel,
                "; ".join(c.strip() for c in cite).rstrip("."),
                fix[:200],
            )
            for rid in ids
        )
    return rules


def collect() -> list[Rule]:
    rules: list[Rule] = []
    for name in REF_FILES:
        rules.extend(parse_ref(REFS / name))
    for _, _, fname, _ in LANGS.values():
        rules.extend(parse_ref(REFS / "lang" / fname))
    return rules


def normalise_codes(name: str, codes: str) -> tuple[str, list[str]]:
    """Return (tool, codes) with ESLint rule names fully qualified."""
    tool = name if name in {"ruff", "mypy", "tsc", "pylint", "gitleaks"} else "eslint"
    prefix = {
        "typescript-eslint": "@typescript-eslint/",
        "jsx-a11y": "jsx-a11y/",
        "eslint-plugin-react": "react/",
        "eslint-plugin-react-hooks": "react-hooks/",
    }.get(name, "")
    out = []
    for raw in re.split(r"[,\s]+", codes):
        tok = raw.strip("()`.;")
        if not tok or tok in TOOL_STOP or tok.endswith("xx") or tok.startswith("--"):
            continue
        if tool in CODE_SHAPE and not CODE_SHAPE[tool].fullmatch(tok):
            continue  # ruff prints "invalid-syntax", which is not a selectable code
        out.append(prefix + tok)
    return tool, out


def build_tool_map(rules: list[Rule]) -> dict[str, object]:
    """Map tool codes to the rules they back. Ruff and mypy codes only map to PY-/X- rules."""
    by_id = {r.rule_id: r for r in rules}
    codes: dict[str, dict[str, list[str]]] = {}
    for r in rules:
        for name, raw in TOOL_GROUP.findall(r.tools):
            tool, toks = normalise_codes(name, raw)
            if tool not in {"ruff", "mypy", "eslint", "tsc"}:
                continue
            py_rule = r.rule_id.startswith("PY-")
            if (
                r.rule_id.startswith("X-") is False
                and (tool in PY_ONLY_TOOLS) != py_rule
            ):
                continue
            for tok in toks:
                lst = codes.setdefault(tool, {}).setdefault(tok, [])
                if r.rule_id not in lst:
                    lst.append(r.rule_id)
    for (tool, tok), concept in PRIMARY.items():
        existing = codes.get(tool, {}).get(tok)
        if not existing:
            continue
        # a primary concept applies to every language prefix: move each match to the front
        existing.sort(key=lambda i: 0 if i.split("-", 1)[1] == concept else 1)
    for tool, toks in ADVISORY.items():
        for tok in toks:
            codes.get(tool, {}).pop(tok, None)
    return {
        "generated_by": "maintainer/gen_checklists.py",
        "rules": {
            rid: {
                "title": r.title,
                "levels": list(r.levels),
                "ref": r.ref,
                "cite": r.cite,
                "fix": r.fix,
            }
            for rid, r in sorted(by_id.items())
        },
        "codes": {t: dict(sorted(c.items())) for t, c in sorted(codes.items())},
        "advisory": ADVISORY,
    }


def source_sha(rel: str) -> str:
    """Last commit that touched a CodeWriter file, for the provenance header."""
    git = shutil.which("git")
    if git is None:
        return "unknown"
    done = subprocess.run(  # noqa: S603 - fixed arguments, no untrusted input
        [git, "log", "-1", "--format=%H", "--", rel],
        capture_output=True,
        text=True,
        cwd=DEV_SKILLS,
        check=False,
    )
    return done.stdout.strip() or "unknown"


# ESLint plugins the fallback uses when they resolve. Others are left to the project's config.
ESLINT_PLUGINS = {
    "@typescript-eslint/": ("typescript-eslint", "tseslint"),
    "react-hooks/": ("eslint-plugin-react-hooks", "reactHooks"),
    "react/": ("eslint-plugin-react", "react"),
    "jsx-a11y/": ("eslint-plugin-jsx-a11y", "jsxA11y"),
    "security/": ("eslint-plugin-security", "security"),
    "n/": ("eslint-plugin-n", "n"),
}


def render_fallbacks(tool_map: dict[str, object]) -> dict[str, str]:
    """Fallback tool configs: select exactly the codes that refs/ maps to a rule."""
    codes = tool_map["codes"]
    if not isinstance(codes, dict):
        raise TypeError("tool map has no 'codes' table")
    ruff_codes = sorted(c for c in codes["ruff"] if c not in FALLBACK_SKIP["ruff"])
    ruff_src = "CodeWriter/python/tooling/ruff.toml"
    mypy_src = "CodeWriter/python/tooling/mypy.ini"
    generated = "Generated by maintainer/gen_checklists.py. Do not edit by hand."
    select = ",\n".join(f'    "{c}"' for c in ["F", *ruff_codes])
    ruff = f"""# ruff.toml: Auditline fallback, used only when the project has no ruff config.
# {generated}
# Provenance: structure and per-file ignores follow {ruff_src} @ {source_sha(ruff_src)}.
# The selection is pyflakes (F: undefined names, unused imports) plus every ruff code that
# refs/ maps to a rule, so a tool result always has a rule ID.
target-version = "py310"

[lint]
preview = true
select = [
{select},
]

# Docstring presence is a nit per function; a project with no docstring convention would drown.
ignore = ["D100", "D101", "D102", "D103", "D104", "D105", "D106", "D107"]

[lint.per-file-ignores]
"**/test_*.py" = ["S101", "S105", "S106", "ARG001", "PLR2004"]
"**/conftest.py" = ["S101"]
"""
    mypy = f"""# mypy.ini: Auditline fallback, used only when the project has no mypy config.
# {generated}
# Provenance: flags adapted from {mypy_src} @ {source_sha(mypy_src)}. Strict flags
# (disallow_untyped_defs and similar) are left off on purpose: a project that does not use them
# would drown the diff in findings. Missing stubs are not findings.
[mypy]
python_version = 3.10
check_untyped_defs = true
no_implicit_optional = true
warn_unreachable = true
warn_return_any = true
strict_equality = true
ignore_missing_imports = true
show_error_codes = true
no_error_summary = true
enable_error_code = unused-coroutine, truthy-bool, ignore-without-code
"""
    eslint_codes = sorted(
        c for c in codes["eslint"] if c not in FALLBACK_SKIP["eslint"]
    )
    groups: dict[str, list[str]] = {"": []}
    for code in eslint_codes:
        for prefix in ESLINT_PLUGINS:
            if code.startswith(prefix):
                groups.setdefault(prefix, []).append(code)
                break
        else:
            if "/" not in code:
                groups[""].append(code)

    def rule_lines(items: list[str]) -> str:
        return "\n".join(f"      '{c}': 'error'," for c in items)

    blocks = [f"    {{ rules: {{\n{rule_lines(groups[''])}\n    }} }},"]
    for prefix, (pkg, var) in ESLINT_PLUGINS.items():
        if prefix in groups:
            blocks.append(
                f"    ...use({var!r}, {pkg!r}, {{\n{rule_lines(groups[prefix])}\n    }}),"
            )
    eslint = f"""// eslint.config.js: Auditline fallback, used only when the project has no ESLint config.
// {generated}
// Provenance: plugin set follows CodeWriter/node/tooling/eslint.config.js; the rules are the ones
// refs/ maps to a finding, not a style guide. A plugin that does not resolve is skipped.
import fs from 'node:fs';
import {{ createRequire }} from 'node:module';

const require = createRequire(process.cwd() + '/');
const typed = fs.existsSync('tsconfig.json');

function load(pkg) {{
  try {{ return require(pkg); }} catch {{ return null; }}
}}

function use(name, pkg, rules) {{
  const mod = load(pkg);
  if (!mod) return [];
  const plugin = name === 'tseslint' ? (mod.plugin ?? mod.default?.plugin) : (mod.default ?? mod);
  const prefix = {{ tseslint: '@typescript-eslint', reactHooks: 'react-hooks', jsxA11y: 'jsx-a11y' }}[name] ?? name;
  const defined = plugin?.rules ?? {{}};
  const usable = (id) => {{
    const rule = defined[id.slice(prefix.length + 1)];
    if (!rule) return false;
    // type-aware rules throw without a tsconfig, so they are left out when there is none
    return typed || !rule.meta?.docs?.requiresTypeChecking;
  }};
  const kept = Object.fromEntries(Object.entries(rules).filter(([id]) => usable(id)));
  const parser = name === 'tseslint' ? (mod.parser ?? mod.default?.parser) : undefined;
  return [{{
    ...(name === 'tseslint' ? {{ files: ['**/*.ts', '**/*.tsx', '**/*.mts', '**/*.cts'] }} : {{}}),
    plugins: {{ [prefix]: plugin }},
    ...(parser ? {{ languageOptions: {{ parser, parserOptions: typed ? {{ projectService: true }} : {{}} }} }} : {{}}),
    rules: kept,
  }}];
}}

export default [
  {{ ignores: ['**/dist/**', '**/node_modules/**', '**/coverage/**', '**/.next/**'] }},
  ...[
{chr(10).join(blocks)}
  ].flat(),
];
"""
    return {"ruff.toml": ruff, "mypy.ini": mypy, "eslint.config.js": eslint}


def render(prefix: str, rules: list[Rule]) -> str:
    folder, label, checklist, tools = LANGS[prefix]
    mine = [r for r in rules if r.rule_id.startswith((f"{prefix}-", "X-"))]
    mine.sort(
        key=lambda r: (
            TIER.index(r.category),
            r.rule_id.split("-")[0] == "X",
            r.rule_id,
        )
    )
    seen: set[str] = set()
    for r in mine:
        if r.rule_id in seen:
            raise SystemExit(f"duplicate rule ID {r.rule_id}")
        seen.add(r.rule_id)
    lines = [
        f"# {label} review checklist",
        "",
        f"Generated by `maintainer/gen_checklists.py` from `refs/`. Do not edit by hand. {len(mine)} rules,",
        "one line per rule ID, in triage order (security, correctness, error handling, performance,",
        "tests, maintainability, diff hygiene). Each line names the level the rule defaults to, the tool",
        "that backs it, and the ref that holds the Detect signal, the WRONG/CORRECT pair and the",
        "citation. Load only the refs a line points at; do not pre-load them.",
        "",
        f"Run first: {tools}. Report their output with `source` set to the tool, and add a model",
        "finding only for what a tool cannot judge. Levels shown are defaults; the rubric in",
        "`refs/severity-and-output-format.md` decides, and a low-confidence blocker or major is a question.",
        "",
    ]
    for cat in TIER:
        group = [r for r in mine if r.category == cat]
        if not group:
            continue
        lines += [f"## {TIER_TITLE[cat]}", ""]
        for r in group:
            lvl = "/".join(r.levels) if r.levels else "see ref"
            tool_text = tools_for(prefix, r.tools)
            tool = f" · {tool_text}" if tool_text else ""
            lines.append(f"- [ ] **{r.rule_id}** {r.title} · {lvl}{tool} · `{r.ref}`")
        lines.append("")
    lines += [
        "## Severity anchors",
        "",
        "`X-SEV-01` to `X-SEV-09` in `refs/severity-and-output-format.md` §5 fix the level of nine",
        "patterns (shared mutable state, query per item, path traversal, always-blocker security",
        "classes, swallowed exception, clickable element without keyboard access, debug output,",
        "hygiene with no runtime effect, hardening absent from the diff). They are not rule IDs.",
        "",
        f"Language rules live in `refs/lang/{checklist}`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--check", action="store_true", help="exit 1 if a generated file is stale"
    )
    args = ap.parse_args()
    rules = collect()
    stale = False
    map_target = OUT / "tool_map.json"
    map_text = json.dumps(build_tool_map(rules), indent=1, ensure_ascii=False) + "\n"
    if args.check:
        if (
            not map_target.exists()
            or map_target.read_text(encoding="utf-8") != map_text
        ):
            print(f"stale: {map_target.relative_to(ROOT)}")
            stale = True
    else:
        map_target.write_text(map_text, encoding="utf-8")
        print(f"wrote {map_target.relative_to(ROOT)}")
    for name, text in render_fallbacks(json.loads(map_text)).items():
        target = FALLBACK / name
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                print(f"stale: {target.relative_to(ROOT)}")
                stale = True
        else:
            FALLBACK.mkdir(exist_ok=True)
            target.write_text(text, encoding="utf-8")
            print(f"wrote {target.relative_to(ROOT)}")
    for prefix, (folder, _, _, _) in LANGS.items():
        target = OUT / f"{folder}-review-checklist.md"
        content = render(prefix, rules)
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                print(f"stale: {target.relative_to(ROOT)}")
                stale = True
        else:
            target.write_text(content, encoding="utf-8")
            print(f"wrote {target.relative_to(ROOT)} ({content.count('- [ ]')} rules)")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
