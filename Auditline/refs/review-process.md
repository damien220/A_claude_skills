# Review process

Sources: Git documentation (`git-diff`, `git-merge-base`, diff format); Google Engineering
Practices, *Code Review Developer Guide* ("What to look for", "Navigating a CL"); tool docs for
ruff, mypy, ESLint and tsc.

## Contents

1. Scope: diff or file
2. Reading a diff
3. Pre-existing issues
4. Language detection
5. Running tools first
6. Reporting skipped and failed tools
7. Large PRs (over 500 changed lines)
8. Security-only mode

## 1. Scope: diff or file

| Situation | Scope | Command |
|---|---|---|
| User names a PR, branch or base | diff | `git diff --merge-base <base>` (Git ≥ 2.30; else `git diff $(git merge-base <base> HEAD)`) |
| No base named, work in progress | diff | staged first: `git diff --cached`; if empty, `git diff` |
| Base unknown | diff | base = `git symbolic-ref --short refs/remotes/origin/HEAD`, else `main`, else `master` |
| User names a path | file | the whole file is in scope; nothing is pre-existing |
| No git repository | file | say so in the report header |

Record the choice in the JSON `scope` (`kind`, `base`, `files`). Never widen a diff review to
the whole repo on your own; if the user wants that, they name the paths.

Cite: Git docs, `git-diff` (`--merge-base`, `--cached`) and `git-merge-base`.

## 2. Reading a diff

- Use `git diff -U10 --merge-base <base>` or read the changed file around each hunk. Three
  lines of context are rarely enough to judge a change.
- **Line numbers come from the new file.** In `@@ -a,b +c,d @@`, the first `+`/context line
  is line `c` of the new file; count only context and `+` lines. Do not count by eye: confirm
  with `grep -n '<text>' <file>` or by reading the file before writing `line`.
- **Removed code can be the defect** (a deleted auth check, a dropped `await`, a removed
  `finally`). Anchor the finding on the nearest new line, quote the removed line with its
  leading `-` in `evidence`, and say what was lost.
- **Follow the value.** A changed function is reviewed together with its callers and callees
  as far as needed to know what reaches it (request input, DB rows, constants) and where its
  result lands (persisted, billed, rendered, returned). Severity depends on both ends.
- Use `git diff -M` so renames do not look like a whole-file rewrite.

WRONG (line taken from the hunk header plus a guess):
```text
@@ -40,6 +40,9 @@ def charge(...):      → finding reported at line 40
```
CORRECT (line of the quoted text in the new file, confirmed):
```text
$ grep -n 'except Exception:' src/billing.py
46:    except Exception:                → finding reported at line 46
```

Cite: Git docs, "diff-format" (unified hunk header `@@ -from +to @@`).
- Generated files, vendored code, lockfiles and snapshots: do not read line by line; check
  only whether the change to them is expected (lockfile churn belongs to diff hygiene).

## 3. Pre-existing issues

An issue is pre-existing when it sits on lines the diff does not change **and** the diff does
not make it newly reachable.

| Case | Treatment |
|---|---|
| Pre-existing blocker in a file the diff touches | report, `"pre_existing": true`, "Pre-existing" section |
| Pre-existing major, minor or nit | do not report |
| Diff adds a new caller that feeds input to old vulnerable code | not pre-existing: rate it as new |
| Diff moves or reformats the old line | not pre-existing: the line is in the diff |
| File scope | nothing is pre-existing |

Pre-existing findings are excluded from `summary` counts and from the verdict.

Cite: Google Engineering Practices, "The Standard of Code Review" (approve a change that
improves code health; do not hold it hostage to problems it did not introduce).

## 4. Language detection

| Signal | Language | Checklist |
|---|---|---|
| `.py`, `pyproject.toml`, `requirements*.txt` | python | `python` |
| `.tsx`, `.jsx`, React imports, `tsconfig.json` with `"jsx"` | typescript | `typescript-react` |
| server `.js`, `.mjs`, `.cjs`, `.ts` with Node imports (`node:`, `fastify`, `express`), `package.json` | node | `node` |

A `.ts` file that imports React or DOM APIs is TypeScript/React; one that imports `node:` modules
or a server framework is Node. When unsure, read the imports. Record every language found in
`scope.languages`.

## 5. Running tools first

Run tools on the files in scope before reading for issues. Never install a tool and never let
`npx` download one.

| Tool | Command (JSON output) | Project config looked for first |
|---|---|---|
| ruff | `ruff check --output-format json <files>` | `ruff.toml`, `.ruff.toml`, `[tool.ruff]` in `pyproject.toml` |
| mypy | `mypy --no-error-summary <files>` (parse `file:line: error: … [code]`) | `mypy.ini`, `.mypy.ini`, `[tool.mypy]`, `setup.cfg` |
| eslint | `npx --no-install eslint -f json <files>` | `eslint.config.*`, `.eslintrc*` |
| tsc | `npx --no-install tsc --noEmit -p <tsconfig>` | `tsconfig.json` |

`python tooling/run_linters.py --base <base>` (or `--staged`, or `--files <paths>` for file
scope) wraps these. It uses the project's config when it finds one and the bundled
`tooling/fallback/` configs otherwise, never installs or downloads a tool, keeps only results on
changed lines in diff scope, and prints one JSON object: `tools` (ran or skipped, with a note),
`findings` (schema-shaped, merged per line), `unmapped` (codes with no rule, for you to triage) and
`dropped` (with the reason). Severity on a tool finding is provisional: it is the lowest level the
rule defaults to; set the real one from the consequence. Use the script when it is present; the
commands in the table are the manual equivalent.

- **Diff scope:** keep only tool results on changed lines (plus pre-existing blockers, §3).
- **Severity:** the tool code sets the rule; the consequence still sets the severity. ruff
  `S608` on request input is a blocker; `F401` is a nit.
- **Do not restate.** A tool result becomes one finding with `source` = the tool and
  `tool_code` = its code(s). If the model adds consequence (e.g. traces a `B006` default into a
  billing total), it goes in `why`; the finding stays tool-sourced. Several codes on one
  defect (`S110`, `BLE001`, mypy `[return]`) merge into one finding.
WRONG (one defect, two findings):
```json
{"line": 102, "rule_id": "PY-ERR-01", "source": "ruff", "tool_code": "S110", "title": "try-except-pass"},
{"line": 102, "rule_id": "PY-ERR-01", "source": "model", "title": "Exception swallowed"}
```
CORRECT (one finding, codes merged, consequence in `why`):
```json
{"line": 102, "rule_id": "PY-ERR-01", "source": "ruff", "tool_code": "S110, BLE001",
 "title": "Charge failure swallowed by except Exception: pass",
 "why": "On the billing path a failed charge becomes None with no log ..."}
```

- **Drop a tool result only with a named reason** (missing stubs, a generated file, a known
  false positive) and write that reason in the tool's `note`.

Example: mypy without the project's dependencies installed reports `Value of type "Row | None"
is not indexable` after `abort(404)`, because `abort` resolves to `Any` and cannot narrow.
Drop it and note `flask not installed; 3 narrowing errors after abort() discarded`.

Cite: ruff docs, "Output formats" (`--output-format json`); ESLint docs, "Formatters" (`-f
json`); npm docs, `npx --no-install`; mypy docs, "Running mypy and managing imports".

## 6. Reporting skipped and failed tools

Every tool relevant to the languages in scope appears in `tools[]`:

```json
"tools": [
  {"name": "ruff", "status": "ran", "note": "project config pyproject.toml"},
  {"name": "mypy", "status": "skipped", "note": "not installed"},
  {"name": "eslint", "status": "skipped", "note": "exited 2: config error in eslint.config.js"}
]
```

A tool that crashed is `skipped` with the error in `note`. When every tool is skipped, the
Markdown header says **model-only review**, so the reader knows no mechanical check backs the
findings.

## 7. Large PRs (over 500 changed lines)

Count with `git diff --shortstat --merge-base <base>` (insertions + deletions).

1. **List files** with `git diff --numstat` and drop generated, vendored, lockfile and snapshot
   files from line-by-line review (name them in the report).
2. **Order by risk:** auth, sessions and permissions → payments and billing → SQL and data
   writes → file, shell and URL handling → public API and schemas → everything else → tests.
3. **Batch per file** (or per small group of related files). Pick topic refs per batch; the
   three-ref cap applies per batch, not per PR.
4. **Run tools once** for the whole change; split their results per batch.
5. **Merge at the end:** dedupe, apply the nit cap across the whole report, compute one verdict.
6. **State coverage** in the header, e.g. `reviewed 14 of 17 files; skipped: package-lock.json,
   2 snapshots`. Never imply full coverage you did not do.

Cite: Google Engineering Practices, "Navigating a CL in review" (look at the main part first)
and "Small CLs".

## 8. Security-only mode

- Scope rules (§1–§3) are unchanged.
- Triage only security: the security ref plus the `-SEC-` items of each language checklist.
- Tools still run (`run_linters.py --security-only`). A tool result is kept as a finding only when
  its **primary** rule is a `-SEC-` rule: ruff `S*`, the ESLint security plugin, `no-eval`,
  `no-implied-eval`, `no-new-func`, `react/no-danger`, `react/jsx-no-script-url`. Results that
  are security-relevant only in context come back as `candidates` for you to promote or discard:
  `no-misused-promises` and `no-floating-promises` when they flag an auth check, `T201` or
  `no-console` when the output holds a secret, `S110` or `BLE001` when the swallowed error is a
  failed security check. Everything else, tsc included, is dropped. The list is the one in
  `refs/security.md` §14.
- Non-security defects are not reported, even blockers; the header states the mode so the
  reader knows the review was partial.
- JSON: `"mode": "security-only"`; every `rule_id` contains `-SEC-` (the schema enforces
  it); the verdict covers security findings only.

Cite: OWASP Code Review Guide 2.0 (security-focused review of source code).
