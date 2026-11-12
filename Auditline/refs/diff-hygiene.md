# Diff hygiene

Sources: Git docs (`git-diff` `-w`, `gitignore`, `git-blame` `--ignore-revs-file`); Google
Engineering Practices, *CL Author's Guide* ("Small CLs", "Separate refactorings") and Google Style
Guides (TODO comments); npm, Poetry and GitHub docs; The Twelve-Factor App; Martin, *Clean Code*
ch. 4; MITRE CWE as cited per rule.

## Contents

1. How to use this ref
2. Rule map
3. Leftovers in the code: DIFF-01, DIFF-02, DIFF-05, DIFF-08
4. What else is in the change: DIFF-03, DIFF-04, DIFF-06, DIFF-07
5. Do not flag

## 1. How to use this ref

- **Rule IDs.** Language-specific rules (debug output) use `PY-DIFF-01`, `NODE-DIFF-01`,
  `TS-DIFF-01`. Language-neutral rules use `X-DIFF-NN`: commented-out code, TODOs, unrelated
  changes, lockfiles, committed artifacts, formatting churn and local-environment leftovers.
  `PY-DIFF-01` is the leftover `print` the P1 sample report uses.
- **Added lines only.** Hygiene rules apply to lines the diff adds or changes. An old `TODO` or an
  old `print` is not this change's finding. In file scope (the user named a path) there is no
  "added line"; apply the rules to the file but cap them at the nit and minor levels.
- **Hygiene is a nit or minor by default.** It rises only when the leftover does something: logs
  secrets (U4), blocks a worker (`breakpoint()`), commits a credential, or points production at
  `localhost`. In those cases the rule below names the finding to file.
- **Collapse tool hits.** ruff `T201`, `T100`, `ERA001`, `FIX002` and ESLint `no-console`,
  `no-debugger`, `no-warning-comments` are tool findings: report them as a count when a tool ran
  (`refs/severity-and-output-format.md` §8) and list at most five model nits.

## 2. Rule map

| ID | Defect | Languages | Default severity |
|---|---|---|---|
| DIFF-01 | Debug output or debugger left in | PY, NODE, TS | nit; minor on a request path; major with secrets/PII (X-SEV-07) |
| X-DIFF-02 | Commented-out code | any | nit |
| X-DIFF-03 | Unrelated changes in the diff | any | minor |
| X-DIFF-04 | Lockfile or manifest churn | any | minor; security if the source changed |
| X-DIFF-05 | TODO without owner or ticket | any | nit |
| X-DIFF-06 | Committed artifact or local file | any | minor; blocker if it holds a secret |
| X-DIFF-07 | Formatting churn hiding the change | any | minor |
| X-DIFF-08 | Local-environment leftover | any | minor; per `-SEC-` rule if it weakens security |

## 3. Leftovers in the code

### PY-DIFF-01 · NODE-DIFF-01 · TS-DIFF-01 — Debug output or debugger left in
- **Detect:** Python: `print(`, `pprint(`, `breakpoint()`, `import pdb` / `pdb.set_trace()`,
  `import ipdb`. JS/TS: `console.log`, `console.debug`, `console.dir`, `console.table`,
  `debugger`, `alert(` used for debugging, `screen.debug()` in tests. X-SEV-07 settles the level.
- **Default severity:** per X-SEV-07: nit in a script, CLI or test; minor on a request path or code
  that runs on every page load; major when it prints secrets, tokens, passwords or PII (U4, and
  then also file `PY-SEC-23` / `NODE-SEC-23` / `TS-SEC-23`). `breakpoint()` and `pdb.set_trace()`
  on a request path are major: with a terminal attached the worker waits for input, and without
  stdin Python raises `BdbQuit` and the request fails.
- **Why:** it bypasses the structured logger and its redaction and levels.
- WRONG:
  ```python
  print("DEBUG invoice", invoice)               # request path, writes to stdout
  breakpoint()                                     # blocks, or raises BdbQuit when stdin is closed
  ```
  ```js
  console.log('session', req.session.token);       // major: token in the logs
  ```
- CORRECT:
  ```python
  logger.debug("invoice built", extra={"customer_id": invoice.customer_id, "items": len(invoice.items)})
  ```
  ```js
  req.log.debug({ userId: req.user.id }, 'session restored');
  ```
- **Fix:** delete it, or use the project logger at `debug` level with no secrets.
- **Cite:** CWE-532; CWE-489 (active debug code); OWASP Logging Cheat Sheet; PEP 282 (logging);
  Python docs, `breakpoint()`.
- **Tool code:** `[ruff: T201, T203, T100]`, `[eslint: no-console, no-debugger]`,
  `[eslint: testing-library/no-debugging-utils]`.

### X-DIFF-02 — Commented-out code
- **Detect:** added comment lines that parse as code (assignments, calls, braces, `return`):
  `# old_total = compute(order)`, `// const token = jwt.sign(...)`, a block of disabled lines
  with `/* … */`. Do not flag: an example inside a docstring, a license header, a directive
  (`# noqa`, `// eslint-disable-next-line`, `# type: ignore`), explanatory pseudocode, or a
  commented example in a sample config.
- **Default severity:** nit (X-SEV-08, n2). Collapse to a count when `ERA001` ran.
- **Why:** readers cannot tell whether it is a warning, a plan or a mistake; version control
  already keeps the old code.
- WRONG:
  ```js
  // const token = jwt.sign({ id: user.id }, JWT_SECRET, { expiresIn: '7d' });
  const token = jwt.sign({ id: user.id, role: user.role }, JWT_SECRET, { expiresIn: '1h' });
  ```
- CORRECT:
  ```js
  const token = jwt.sign({ id: user.id, role: user.role }, JWT_SECRET, { expiresIn: '1h' });
  ```
- **Fix:** delete it; if it records a decision, replace it with one sentence saying why.
- **Cite:** Martin, *Clean Code* ch. 4, "Commented-Out Code"; SonarSource rule S125.
- **Tool code:** `[ruff: ERA001]`; none for JS.

### X-DIFF-05 — TODO without owner or ticket
- **Detect:** a newly added `TODO`, `FIXME`, `HACK` or `XXX` with no `(name)` and no ticket link.
  If the comment marks missing behavior on a shipped path (`# TODO: check permissions`,
  `// TODO: validate input`), report the missing behavior under its own rule (security or
  correctness) and quote the TODO as evidence; the hygiene nit is then dropped.
- **Default severity:** nit.
- **Why:** an unowned note is never found again, and it hides known gaps.
- WRONG:
  ```python
  # TODO: handle refunds
  ```
- CORRECT:
  ```python
  # TODO(billing-team, PAY-482): handle partial refunds; full refunds only for now.
  ```
- **Fix:** add an owner and a ticket, or do it now, or delete the note.
- **Cite:** Google Style Guides (Python, C++), "TODO Comments" (name or bug ID in parentheses).
- **Tool code:** `[ruff: TD002, TD003, FIX001, FIX002]`, `[eslint: no-warning-comments]`.

### X-DIFF-08 — Local-environment leftover
- **Detect:** a base URL of `localhost` / `127.0.0.1` / `http://localhost:3000` as a default in
  shared or production config; the author's absolute paths (`/Users/alice/`, `C:\Users\`);
  `DEBUG = True` or `NODE_ENV=development` in a production file; sample credentials or test tokens
  outside tests; a check disabled "for now" (`verify=False`, `rejectUnauthorized: false`,
  `// TEMP`, `if (true) // was: isAdmin(user)`); a feature flag forced on.
- **Default severity:** minor; major when it breaks production configuration (a `localhost` API
  URL as the default, C2/R1). When it weakens security, file it under the `-SEC-` rule:
  `PY-SEC-12` / `NODE-SEC-12` (TLS verification off), `PY-SEC-18` / `NODE-SEC-18` (debug mode),
  `PY/NODE/TS-SEC-02` (credential), `PY/NODE/TS-SEC-04` (an ownership or role check bypassed),
  `PY/NODE-SEC-24` (a check that fails open).
- **Why:** these values work on the author's machine and fail, or open a hole, anywhere else.
- WRONG:
  ```js
  const API_URL = process.env.API_URL ?? 'http://localhost:4000';      // production falls back to localhost
  const agent = new https.Agent({ rejectUnauthorized: false });        // TEMP
  ```
- CORRECT:
  ```js
  const API_URL = process.env.API_URL;
  if (!API_URL) throw new Error('API_URL is required');
  ```
- **Fix:** read configuration from the environment and fail fast when it is missing; remove
  temporary bypasses.
- **Cite:** The Twelve-Factor App, III "Config"; CWE-489; CWE-798 for credentials.
- **Tool code:** none (`[ruff: S501]` for `verify=False`).

## 4. What else is in the change

### X-DIFF-03 — Unrelated changes in the diff
- **Detect:** hunks or files with no link to the stated purpose of the change (branch, title or
  commit message): a drive-by rename, a reformat of untouched code, an unrelated dependency bump,
  a second feature. Judge by the description, not by your taste. Report **once** per diff, at the
  first example, naming the others.
- **Default severity:** minor (C3: harder to review and to revert). Nit if it is a few lines.
  A behavior change hidden inside a "refactor" or "formatting" hunk is filed under the rule of
  that behavior.
- **Why:** a reviewer approves the stated change and the rest rides along unseen.
- WRONG:
  ```text
  Title: Fix rounding in invoice totals
  Files: billing/totals.py, billing/tax.py (rewritten), web/templates/base.html (renamed CSS classes)
  ```
- CORRECT:
  ```text
  Title: Fix rounding in invoice totals
  Files: billing/totals.py, tests/test_totals.py     (the tax rewrite and CSS rename: separate changes)
  ```
- **Fix:** split into separate changes; submit refactors on their own.
- **Cite:** Google Engineering Practices, *CL Author's Guide*, "Small CLs" and "Separate
  refactorings from feature changes".
- **Tool code:** none.

### X-DIFF-04 — Lockfile or manifest churn
- **Detect:** a manifest (`package.json`, `pyproject.toml`, `requirements.txt`) changed with its
  lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `poetry.lock`, `uv.lock`)
  unchanged, or the reverse; a lockfile diff far larger than the manifest change (regenerated with
  another tool version, mass transitive bumps); two lockfiles for one package manager; unpinned
  additions in a pinned `requirements.txt`; a `resolved` URL that is not the project's registry, or
  a removed `integrity` hash (these are supply-chain changes: file them under `X-SEC-01`).
- **Default severity:** minor; major when the lockfile and manifest disagree so that `npm ci` or
  the CI install fails. Do not read lockfiles line by line: check only that the change is expected.
- **Why:** installs stop being reproducible, and a transitive bump arrives without review.
- WRONG:
  ```text
  package.json:   + "zod": "^3.23.0"
  package-lock.json: (not in the diff)           # npm ci fails: lockfile out of sync
  ```
- CORRECT:
  ```text
  package.json:       + "zod": "^3.23.0"
  package-lock.json:  zod added, only its own entry changed
  ```
- **Fix:** regenerate the lockfile with the project's package-manager version and commit both;
  revert unrelated lockfile movement.
- **Cite:** npm docs, `package-lock.json` (commit it) and `npm ci` (exits with an error when
  the lockfile and `package.json` disagree); Poetry docs, "Commit your `poetry.lock` file".
- **Tool code:** none.

### X-DIFF-06 — Committed artifact or local file
- **Detect:** `.env` with values, `*.pem`, `id_rsa`, `__pycache__/`, `*.pyc`, `node_modules/`,
  `dist/`, `build/`, `.DS_Store`, `.idea/`, personal `.vscode/` settings, coverage output, logs,
  database files or dumps (`*.sqlite`, `*.dump`), archives, large binaries, and `.auditline/`
  reports. Check `.gitignore` for the pattern.
- **Default severity:** minor (repo hygiene). A file that holds a credential or key is a blocker
  under `PY/NODE/TS-SEC-02` (X-SEV-04): rotate the secret, since deleting the file leaves it in
  history. A large binary is minor.
- **Why:** they bloat the repository, leak local detail, and conflict between contributors.
- WRONG:
  ```text
  A  .env                       # contains DATABASE_URL=postgres://admin:s3cr3t@…
  A  src/__pycache__/app.cpython-313.pyc
  ```
- CORRECT:
  ```text
  A  .env.example               # keys with placeholder values
  M  .gitignore                 # + .env, __pycache__/, dist/
  ```
- **Fix:** remove the file from the index (`git rm --cached`), add a `.gitignore` entry, commit an
  `.example` file; rotate any exposed secret.
- **Cite:** Git docs, `gitignore`; GitHub docs, "Removing sensitive data from a repository";
  CWE-540 (sensitive information in source code); CWE-798.
- **Tool code:** `[gitleaks]` for secrets when installed.

### X-DIFF-07 — Formatting churn hiding the change
- **Detect:** the diff reindents a whole file, changes line endings, reorders imports or
  reformats code the change does not touch, so that the real change is a few lines among
  hundreds. Compare `git diff --stat` with `git diff -w --stat`: if most of the difference
  disappears with `-w`, it is churn.
- **Default severity:** minor; nit when under about 20 lines.
- **Why:** reviewers cannot find the logic change, and `git blame` now points at the formatter.
- WRONG:
  ```text
  git diff --stat      → 412 lines changed in 1 file
  git diff -w --stat   →   9 lines changed in 1 file
  ```
- CORRECT:
  ```text
  commit 1: "Format with black"   (listed in .git-blame-ignore-revs)
  commit 2: "Fix rounding in totals"   (9 lines)
  ```
- **Fix:** separate the formatting commit, or revert the formatting hunks; add the formatting
  commit to `.git-blame-ignore-revs`.
- **Cite:** Git docs, `git-diff` (`-w`) and `git-blame` (`--ignore-revs-file`); Google
  Engineering Practices, "Small CLs".
- **Tool code:** none.

## 5. Do not flag

| Pattern | Why it is not a finding |
|---|---|
| `print` or `console.log` in a CLI, script, build tool or test whose output is the product | that is its output channel (n4, X-SEV-07) |
| `print` in a one-off migration or notebook | R3: nit at most |
| A `TODO` that already existed and the diff did not touch | not this change |
| Commented-out lines that are directives, examples or license text | not code |
| Lockfile changes that match the manifest change | expected |
| A formatter-only commit that is separate from the logic change | exactly what is asked for |
| `.env.example`, `.gitignore`, `.gitattributes`, `.editorconfig` | meant to be committed |
| Generated or vendored files named in the repository's `.gitattributes` (`linguist-generated`) | check only that the change is expected |
