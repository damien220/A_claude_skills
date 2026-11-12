# Auditline — How To Use

## What it does

Auditline **reviews** Python, Node.js and TypeScript/React code and reports findings. It never
edits the code under review and never calls the GitHub API. Each finding has a severity
(blocker, major, minor, nit), a `file:line` anchor, the quoted line, a cited source (OWASP, CWE,
PEP, RFC, WCAG or official docs), a suggested fix and a confidence. Every run ends with a verdict
and writes two reports: Markdown for people and JSON for tools.

Auditline is the review companion to CodeWriter: CodeWriter teaches how to *write* code, Auditline
checks code that already exists against the same standard.

---

## Prerequisites

- Claude Code installed and running.
- Nothing else is required. The scripts need Python 3.10+ and use only the standard library.
- Optional, and used when present: `ruff`, `mypy` (Python) and `eslint`, `tsc` (Node and
  TypeScript). Anything missing is reported as skipped, and a review with every tool skipped says
  "model-only review" in its header. Auditline never installs or downloads a tool.

---

## Setup

Copy the whole `Auditline/` directory (not only `SKILL.md`; the refs and tooling are part of the
skill) into a skills location:

```bash
# This project only
cp -r Auditline /path/to/your-project/.claude/skills/auditline

# All your projects
cp -r Auditline ~/.claude/skills/auditline
```

To keep it in sync with edits instead of copying, symlink the directory:

```bash
ln -s "$(pwd)/Auditline" ~/.claude/skills/auditline
```

The `maintainer/` directory is for people who work on the skill and is not needed to use it.
Remove it from the copy if you want a smaller install.

Check the install: start `claude` in any project and ask "review this file src/foo.py". The
skill's name, `auditline`, should appear when Claude reads its instructions.

---

## Usage

Ask in plain words. All of these load the skill:

| You say | What happens |
|---|---|
| `review this diff` | Reviews the git diff against the base branch (the merge base), changed lines plus the context needed to read them |
| `review this PR` | Same, for the current branch |
| `review src/api/orders.mjs` | Reviews that whole file; no git context is needed |
| `audit this code` / `what's wrong with this code` | Reviews what you point at, or the diff when nothing is named |
| `security review only` (`--security-only`) | Security rules only; other defects are not reported, even blockers, and the report says the review was partial |

You can name the base and the report paths in the same sentence ("review this diff against
`develop`, write the report to `reviews/pr-42.md`"). Without a path, the reports go to
`.auditline/report.md` and `.auditline/report.json` in the project root.

### Steps a review follows

1. **Scope.** The diff by default; a whole file only when you name a path or there is no git.
2. **Language.** Detected from extensions and manifests; one checklist is loaded per language.
3. **Tools first.** `tooling/run_linters.py` runs the installed linters on the changed lines, using
   your project's config when there is one and the bundled fallback when there is not. Tool output
   is evidence and is reported with its tool as the source.
4. **Triage in a fixed order:** security, correctness, error handling, performance, tests,
   maintainability, diff hygiene. Only the reference files that match the change are read: the
   language checklist plus at most three topic refs (more only for a diff over 500 lines).
5. **Final gate.** Every finding has a line whose text matches its quote, duplicates are merged,
   nits are capped at five, and the verdict matches the highest severity.

### Reading the report

````markdown
### [blocker] `src/routes/orders.mjs:27` NODE-SEC-01: Order id from the URL concatenated into SQL

```js
const { rows } = await db.query(`SELECT * FROM orders WHERE id = ${req.params.id}`);
```

**Why:** `req.params.id` reaches the SQL text on `GET /orders/:id`, which any logged-in customer
can call, so `1 OR 1=1` returns every customer's orders.
**Fix:** `await db.query('SELECT * FROM orders WHERE id = $1 AND customer_id = $2', [req.params.id, req.user.id])`
**Cite:** CWE-89; OWASP A03:2021 Injection
**Source:** model · confidence: high
````

| Level | Meaning | Example |
|---|---|---|
| blocker | Exploitable by anyone, or data or money lost on a common path | SQL built from a URL parameter |
| major | A real bug a trusted user or an unlucky request hits, or a missing test for auth or money logic | N+1 query on a list endpoint |
| minor | Real cost, low blast radius | Misleading name, missing type on a public function |
| nit | Style a tool can fix | Unused import |

Severity is the consequence if the defect triggers, weighed against who can trigger it, not the
name of the pattern. A finding the reviewer is not sure of at blocker or major level is reported
as a **question**, not a finding.

**Verdict:** `request changes` when there is any blocker or major, `approve with nits` when there
are only minors and nits, `approve` when there are no findings. Questions never change it, and a
pre-existing blocker is added to the verdict line without changing it. A script checks the verdict
against the findings.

### Rule IDs

`<LANGUAGE>-<CATEGORY>-<NN>`: `PY-SEC-01`, `NODE-ERR-05`, `TS-COR-11`, and `X-DIFF-02` for rules
that hold in every language. Categories: `SEC` security, `COR` correctness, `ERR` error handling,
`PERF` performance, `TEST` tests, `MAINT` maintainability, `DIFF` diff hygiene, `OPS` deployment
files, `ACC` accessibility. The same number is the same defect in every language. Each ID is
defined once in `refs/`, with its signal, default severity, WRONG and CORRECT examples, fix and
citation.

---

## Running the scripts yourself

All scripts are standard-library Python. Run them from the `Auditline/` directory.

```bash
# What the linters say about your change (JSON: tools, findings, unmapped, dropped)
python tooling/run_linters.py --root /path/to/project --base main
python tooling/run_linters.py --root /path/to/project --staged
python tooling/run_linters.py --root /path/to/project --files src/app.py
python tooling/run_linters.py --root /path/to/project --base main --security-only

# Point at a tool that is not on PATH
python tooling/run_linters.py --files src/app.py --tool ruff=/path/to/ruff

# Check a finished report (schema, quoted lines match the files, no duplicates,
# verdict consistent, nit cap, sort order, Markdown agrees with JSON)
python verification/validate_report.py .auditline/report.json --md .auditline/report.md --root /path/to/project
```

`run_linters.py` keeps only results on changed lines when you give it a diff scope, maps each tool
code to a rule ID through `tooling/tool_map.json`, and puts codes it has no rule for in `unmapped`
rather than inventing a rule. In `--security-only` mode a result counts as a finding only when its
rule is a security rule; other hits come back as `candidates` for the reviewer to promote or drop.

---

## Example session

(Illustrative output; the shape is real, the findings are made up.)

```text
$ cd ~/work/shop-api && claude
> review this diff

Auditline: scope = git diff --merge-base main (3 files: src/routes/orders.mjs, src/db.mjs, test/orders.test.mjs)
Tools: eslint ran (project config), tsc skipped (no tsconfig.json)
Reading: refs/lang/node-checklist.md, refs/security.md, refs/correctness.md, refs/tests.md

Verdict: request changes   (1 blocker, 2 major, 1 minor, 2 nits)

[blocker] src/routes/orders.mjs:27 NODE-SEC-01  Order id from the URL concatenated into SQL
[major]   src/routes/orders.mjs:41 NODE-COR-09  total += await inside Promise.all loses updates
[major]   test/orders.test.mjs:12  NODE-TEST-06 it.only committed: the rest of the file is skipped
...
Reports written: .auditline/report.md, .auditline/report.json
```

---

## Verifying the skill itself

Run these after editing anything under `refs/`, in this order:

```bash
python maintainer/gen_checklists.py       # regenerate tooling/*-review-checklist.md, tool_map.json, fallback/
python verification/lint_skill.py         # frontmatter, routing, ref shape, rule IDs, code blocks
python verification/test_scripts.py       # scripts and scorer (52 tests; some skip if tools are missing)
python verification/check_corpus.py       # the seeded-defect corpus is consistent with its files
python maintainer/check_drift.py          # only when CodeWriter changed: stale provenance
```

`lint_skill.py` fails when a rule lacks one of its eight fields, an ID is duplicated or undefined,
a ref is not routed from `SKILL.md`, the tooling checklists drift from the refs, or a shipped file
points at a sibling directory.

### Scoring a review against the corpus

`verification/` holds, per language, files with seeded defects (63 in all, 30 of them hard-tier),
clean control files with decoys (correct code that looks wrong), and an `expected.json` with the
ground truth and a written severity rationale for every defect.

```bash
python verification/score.py verification/python/expected.json my_report.json --summary
python verification/score.py verification/node/expected.json my_report.json --security-only
```

The scorer reports recall (overall, blocker+major, hard tier), severity exact-match and within one
level, extra findings, false positives on decoys, blockers or majors reported on clean files and
rule-ID agreement. Do not show `expected.json` to a reviewer under test.

### Rebuilding the A/B evaluation (maintainers)

The evaluation compares a reviewer with the skill against the same reviewer without it, on Haiku,
Sonnet and Opus. The scratch directory is session-local; saved results are in
`maintainer/eval_round1/` and `maintainer/eval_round2/`.

1. Install the TypeScript toolchain into a scratch directory with
   `npm install --legacy-peer-deps` (eslint@9, **typescript@5.9.3**, typescript-eslint, the React,
   hooks, jsx-a11y, security and n plugins, `@eslint/js`, globals, react, react-dom, the `@types`
   packages, TanStack Query, next, vitest, Testing Library, zod). Do not run two installs in the
   same directory at once.
2. Build the bundles. `--node-modules` is the `node_modules` directory itself:
   ```bash
   python maintainer/prepare_eval.py --out EVAL/skillbundle --truth-out EVAL/truth --node-modules NM/node_modules
   python maintainer/prepare_eval.py --no-skill --out EVAL/plainbundle --node-modules NM/node_modules
   ```
   The corpus files are copied under neutral names (`module_a` to `module_e`) so a reviewer cannot
   tell a clean file from a bad one; the name map stays in `EVAL/truth`.
3. Pre-flight: run the bundled `run_linters.py` on a TypeScript file and check that both `eslint`
   and `tsc` say `ran`.
4. Write one prompt per run, then give each reviewer agent that prompt file:
   `python maintainer/eval_prompts.py EVAL LANG MODEL skill|plain > EVAL/runs/prompt_LANG_MODEL_COND.txt`
5. Score: `python maintainer/eval_report.py --eval EVAL --json OUT [--tasks <transcript dir>]`.
   Pass `--tasks` with saved transcripts to fill the routing column (which refs were read) and
   run the leak check.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The skill does not load on "review this diff" | The directory must be `…/skills/auditline/` containing `SKILL.md`; a lone `SKILL.md` is missing its refs. Restart `claude` after copying. |
| CodeWriter loads instead of Auditline | Ask for the action in the review verbs ("review", "audit"). "Write" and "refactor" belong to CodeWriter, which does not review. |
| Report says "model-only review" | No linter was found. Install ruff, mypy, eslint or tsc in the project, or pass `--tool NAME=PATH`. |
| eslint or tsc skipped on a TypeScript project | The tool must be reachable as `node_modules/.bin/<tool>` under `--root`, or on PATH. A project whose ESLint rejects every file is reported as skipped with the reason, not as a clean run. |
| `validate_report.py` says a quote does not match the line | The line number drifted (the file changed after the review, or the anchor was off). Re-run the review on the current file. |
| A security-only report shows a non-security rule ID | The schema forbids it in that mode; rule it as a `-SEC-` finding (cross-user data and bypassed checks are `-SEC-04`) or drop it. |
| Too many findings on a large diff | Over 500 changed lines the review is batched per file. Ask for `--security-only`, or name the files that matter. |

---

## Limits

- It reads the code it is given. A fix in a file the diff does not show (a gateway, a shared
  helper) can make a finding wrong; the report lowers the confidence or asks a question.
- It does not report the absence of a control it cannot see (no helmet, no rate limiting) as a
  defect.
- A review costs about 4 to 5 times the tokens of an unguided review in the evaluation (it reads
  the checklist, the matching refs and the linter output). That buys the cited, line-anchored,
  severity-calibrated report.
- Rules were checked against the tool versions installed when they were written. Documentation
  page titles in citations that were written from memory are listed in `plan.md` for re-checking.
