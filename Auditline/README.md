# Auditline

A Claude Code skill that **reviews** Python, Node.js and TypeScript/React code. It reports
findings; it never edits the code under review. Every finding names a file and a line, quotes
the offending text, carries a severity, a citation (OWASP, CWE, PEP, RFC, WCAG or official docs)
and a suggested fix, and every run ends with a verdict: **approve**, **approve with nits** or
**request changes**.

Use it on a diff before you commit, on a pull request, or on a file you name. Ask in plain
words: "review this diff", "audit src/billing.py", "what's wrong with this code", or "security
review only".

## What it does and does not do

| It does | It does not |
|---|---|
| Review the git diff by default, or a named file | Rewrite, refactor or generate code |
| Run ruff, mypy, eslint and tsc first when installed, and report their output as evidence | Install tools or download anything |
| Rate severity by consequence and reachability, not by the name of the pattern | Post comments or call the GitHub API |
| Say when it is not sure: a low-confidence blocker becomes a question, not a finding | Report the absence of a control it cannot see (no helmet, no rate limiting) as a defect |
| Write a Markdown report and a JSON report on every run | Review architecture beyond what the diff touches |

See [`howto.md`](howto.md) for the full walk-through.

## Quick start

Copy this directory into your skills location:

```bash
cp -r Auditline /path/to/your-project/.claude/skills/auditline   # this project only
cp -r Auditline ~/.claude/skills/auditline                       # all your projects
```

Then, in Claude Code:

```text
review this diff
review src/api/orders.mjs
security review only (--security-only)
```

Reports are written to `.auditline/report.md` and `.auditline/report.json` in the project root
unless you name other paths.

## What a finding looks like

````markdown
### [blocker] `src/routes/orders.mjs:27` NODE-SEC-01: Order id from the URL concatenated into SQL

```js
const { rows } = await db.query(`SELECT * FROM orders WHERE id = ${req.params.id}`);
```

**Why:** `req.params.id` reaches the SQL text on `GET /orders/:id`, which any logged-in customer
can call (signup is open), so `1 OR 1=1` returns every customer's orders.
**Fix:** `await db.query('SELECT * FROM orders WHERE id = $1 AND customer_id = $2', [req.params.id, req.user.id])`
**Cite:** CWE-89; OWASP A03:2021 Injection
**Source:** model · confidence: high
````

Severity follows a rubric: the consequence if it triggers (data or money lost, attacker access,
wrong result, latency, readability) against who can trigger it (anyone, a trusted user, nobody).
Four levels: **blocker**, **major**, **minor**, **nit**. The verdict follows from the highest level.

## Modes

- **full** (default): security, correctness, error handling, performance, tests,
  maintainability, diff hygiene, in that order.
- **`--security-only`**: security rules only, same report layout; non-security defects are not
  reported, even blockers, and the report says the review was partial.

## How it works

1. **Scope.** The diff against a base, staged changes, or the files you name.
2. **Languages.** Detected from extensions and manifests; one checklist per language present.
3. **Tools first.** `tooling/run_linters.py` runs the installed linters on the changed lines,
   with your config when there is one and the bundled fallback otherwise, and maps each result
   to a rule.
4. **Triage in a fixed order**, loading only the reference files that match the change. At most
   three topic references plus the language checklist per review (more only for diffs over 500
   lines, batched per file).
5. **Final gate.** Every finding has a line whose text matches its quote, duplicates are merged,
   nits are capped at five, and the verdict matches the highest severity. `verification/validate_report.py`
   checks this mechanically.

## Layout

```
Auditline/
├── howto.md                       step-by-step usage, scripts, evaluation rebuild, troubleshooting
├── SKILL.md                       entry point: 18 titles, each with a "Read refs/… when:" trigger
├── refs/
│   ├── review-process.md          scope, reading a diff, tools, large diffs, security-only mode
│   ├── severity-and-output-format.md   the rubric, 9 calibration anchors, report formats
│   ├── security.md                OWASP Top 10:2021, 28 rules with CWE IDs
│   ├── correctness.md  performance.md  error-handling.md  tests.md  maintainability.md  diff-hygiene.md
│   └── lang/                      python / node / typescript-react checklists
├── tooling/
│   ├── finding.schema.json        JSON Schema (draft 2020-12) of the report
│   ├── report-template.md         the Markdown layout
│   ├── run_linters.py             runs ruff, mypy, eslint, tsc; maps results to rules
│   ├── tool_map.json              tool code to rule ID
│   ├── *-review-checklist.md      one line per rule for each language
│   └── fallback/                  ruff.toml, mypy.ini, eslint.config.js for projects with none
└── verification/                  seeded-defect corpus, scorer, lint and report validator, tests
```

Reference files are never pre-loaded: `SKILL.md` carries the rules that are always on, and each
reference is read only when the change matches its trigger.

## Rule IDs

`<LANGUAGE>-<CATEGORY>-<NN>`: `PY-SEC-01`, `NODE-ERR-05`, `TS-COR-11`, `X-DIFF-02` for rules that
are the same in every language. Categories: `SEC` security, `COR` correctness, `ERR` error
handling, `PERF` performance, `TEST` tests, `MAINT` maintainability, `DIFF` diff hygiene, `OPS`
deployment files, `ACC` accessibility. The same number is the same defect in every language.
Each rule has a signal to look for, a default severity, the reason, a WRONG and a CORRECT
example, the fix, a citation and the tool code that backs it.

## Requirements

None to use the skill. The scripts need Python 3.10+ and use only the standard library. The
linters are optional: whatever is installed is used, and anything missing is reported as skipped
(a review with every tool skipped says "model-only review" in its header).

## Checking the skill

```bash
python verification/lint_skill.py        # structure, routing, rule IDs, references, code blocks
python verification/test_scripts.py      # scripts and scorer
python verification/check_corpus.py      # the seeded-defect corpus
```

`verification/` holds a corpus of files with seeded defects per language, clean control files
that contain decoys (correct code that looks wrong), and `score.py`, which scores any set of
findings against the ground truth: recall, severity accuracy, false positives on decoys, and
blockers reported in clean files.

## Evaluation

The skill was scored against a seeded-defect corpus (63 defects: 21 Python, 20 Node, 22
TypeScript, 30 of them hard-tier, plus clean controls with decoys) on Haiku, Sonnet and Opus, with
and without the skill, using the same scorer for both. Means over 9 runs per condition (round 2):

| Metric | With Auditline | Without |
|---|---|---|
| Recall, all defects | 95.8% | 83.3% |
| Recall, blocker + major | 96.9% | 89.2% |
| Recall, hard tier | 97.8% | 86.7% |
| Recall, security slice | 97.8% | 91.1% |
| Severity exact match | 89.1% (within one level: 100%) | 82.5% |
| Unseeded extra findings (196 vs 211 findings) | 15 | 53 |
| Blocker or major reported on clean files | 0 | 8 |
| Rule ID and citation on a finding | 100% | 0% |

Every report passes `verification/validate_report.py` (quoted line equals the file line). A third
round re-ran the three TypeScript skill runs after the test-mocking rule was tightened: recall
100% / 95% / 100% (Haiku / Sonnet / Opus), blocker + major 100% on all three, and the always-granting
membership mock (`TS-TEST-07`) was found by all three. Results are in `maintainer/eval_round1/`,
`eval_round2/` and `eval_round3/`.

**Cost.** A review uses roughly 4 to 5 times the tokens of an unguided review (about 150k to 220k
per run on the corpus, against 12k to 60k without the skill). That is the price of reading the
checklist, the matching references and the linter output.

**Not yet measured:** the trigger test (does "review this diff" load Auditline and "write a
Fastify route" load CodeWriter), the routing check on real transcripts, and the security-only
slice as separate runs. Precision is a lower bound: all extras are counted as wrong, and a manual
verdict can only raise it.

## Limits

- It reads the code it is given. A fix that lives in a file the diff does not show (a gateway,
  a shared helper) can make a finding wrong; it says so by lowering confidence or asking a question.
- A review is as strong as its evidence. Tool output is evidence; the model's own findings are the
  layer on top.
- Rules are checked against the tools installed when they were written; citations to
  documentation pages are listed in the project plan for re-checking.
