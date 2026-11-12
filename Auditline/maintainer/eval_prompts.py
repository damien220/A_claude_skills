"""Emit the reviewer prompt for one evaluation run (maintainer tool, not shipped).

    python maintainer/eval_prompts.py EVAL_DIR LANG MODEL skill|plain

EVAL_DIR holds skillbundle/, plainbundle/, truth/ and runs/ (see prepare_eval.py). Python runs
need the tool paths in AUDITLINE_RUFF and AUDITLINE_MYPY. Write each output to
EVAL_DIR/runs/prompt_<lang>_<model>_<cond>.txt and tell the reviewer agent to read that file.
"""

import os
import sys

R = sys.argv[1]
RUFF = os.environ.get("AUDITLINE_RUFF", "ruff")
MYPY = os.environ.get("AUDITLINE_MYPY", "mypy")
FILES = {
    "python": "module_a.py module_b.py module_c.py module_e.py test_module_e.py",
    "node": "module_a.mjs module_b.mjs module_c.mjs module_e.mjs module_e.test.mjs",
    "typescript": "module_a.tsx module_b.tsx module_c.tsx module_e.tsx module_e.test.tsx",
}
lang, model, cond = sys.argv[2:5]
out = f"{R}/runs/{lang}_{model}_{cond}"
if cond == "skill":
    B = f"{R}/skillbundle"
    tools = ""
    if lang == "python":
        tools = f"Pass `--tool ruff={RUFF} --tool mypy={MYPY}` to run_linters.py so it finds the installed tools. "
    print(f"""You are performing code reviews with the Auditline code-review skill.

The skill is installed at {B}/skill/auditline . Start by reading {B}/skill/auditline/SKILL.md and follow it exactly as it instructs: it tells you which reference files to read and when, which tools to run first, how to rate severity, what the report looks like, and the final gate. Do not pre-load reference files the skill does not call for.

Project root to review: {B}/inputs/{lang}
Files: {FILES[lang]}
Treat each file as its own file-scope review (choose the references for each file as the skill directs), and write ONE combined report covering all five files: each finding's `file` is the file name relative to the project root; `scope.kind` is "file" and `scope.files` lists all five.

Tooling: the skill's tooling/run_linters.py runs the linters. Use `--root {B}/inputs/{lang} --files <names>`. {tools}Never install anything.

Output: write the JSON report to {out}.json and the Markdown report to {out}.md (not to .auditline/). Then run the skill's final gate: python {B}/skill/auditline/verification/validate_report.py {out}.json --md {out}.md --root {B}/inputs/{lang} and fix the report until it passes (at most 3 attempts; if it still fails, say what failed). Also write {out}.notes.txt listing, for each file, the skill reference files you read for it.

Rules: this is review only; do not edit any file under {B}. Do not read anything outside {B}/skill/auditline and {B}/inputs/{lang}; in particular look for no ground truth, answer key, test expectations or baseline results anywhere. Your final message is one line: the number of findings by severity.""")
else:
    B = f"{R}/plainbundle"
    print(f"""You are an expert code reviewer. Review the following files, which are in {B}/inputs/{lang}/ : {FILES[lang]}

Read only those files. Do not read or run anything else, do not edit any file, and do not look for answer keys or other results.

Report real problems only, each with:
- file: the file name, as listed above
- line: the 1-based line number of the offending line
- severity: one of blocker (exploitable security flaw, data loss or corruption, crash on a common path, leaked secret), major (likely bug, unhandled failure at an I/O boundary, quadratic cost on a hot path, new logic with no tests, race condition), minor (non-idiomatic code with a real cost), nit (style a linter can autofix)
- category: one of security, correctness, error-handling, performance, tests, maintainability, diff-hygiene
- title: one short sentence naming the defect
- evidence: the offending line copied verbatim
- confidence: high, medium or low

Write the result as JSON, {{"findings": [ ... ]}}, to {out}.json . Your final message is one line: the number of findings by severity.""")
