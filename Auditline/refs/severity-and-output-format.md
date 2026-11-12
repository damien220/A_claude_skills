# Severity and output format

Sources: FIRST, CVSS v4.0 specification (impact vs exploitability, the model for consequence vs
reachability); MITRE CWE; OWASP Top 10:2021; WCAG 2.2; Google Engineering Practices, *Code
Review Developer Guide*; Conventional Comments (conventionalcomments.org); Python and React
docs as cited per item.

## Contents

1. Rubric: consequence × reachability
2. Upgrade and downgrade rules
3. Confidence, questions and pre-existing issues
4. Worked examples per level
5. Calibration anchors (X-SEV-01 … X-SEV-09)
6. Noise suppression
7. Output format: Markdown and JSON
8. Nits: collapsing and the cap
9. Verdict rules

## 1. Rubric: consequence × reachability

Answer two questions before choosing a level, and write both answers in `why`:

1. **Consequence:** what breaks, for whom, if it triggers? Trace the value to where it lands
   (aliased into a returned object, persisted, billed, used in an auth decision, rendered).
   Rate the outcome on this code path, not the pattern's name.
2. **Reachability:** who can trigger it and how often?

| Consequence class | Meaning |
|---|---|
| **C1 critical** | attacker gains access, data or code execution; a secret is exposed; data or money is corrupted or lost; crash or wrong result on a common path; public contract broken |
| **C2 serious** | wrong result or failure under specific conditions; unhandled failure at an I/O boundary; per-request latency or availability cost; information exposure that aids an attack; new logic without tests |
| **C3 cost** | contained cost: misleading name, debug noise, a11y gap on a secondary control, missing type on a public API |
| **C4 cosmetic** | autofixable style, unused names, commented-out code |

| Reachability | Meaning |
|---|---|
| **R1 open** | any caller (anonymous or self-registered), every request, the default code path, unbounded data |
| **R2 gated** | only trusted users behind an authorization check **visible in code**, rare inputs, small bounded data |
| **R3 unreachable** | dead code, tests, fixtures, one-off local scripts |

| | R1 | R2 | R3 |
|---|---|---|---|
| **C1** | blocker | major | minor |
| **C2** | major | minor | nit |
| **C3** | minor | minor | nit |
| **C4** | nit | nit | nit |

**Never downgraded below blocker** (X-SEV-04): a hardcoded production secret (the leak happens
at commit, so reachability is irrelevant), and injection, auth bypass or stored XSS reachable by
anyone who can sign up.

The baseline's main error was under-rating C1 consequences because the reviewer stopped at the
pattern ("mutable default", "N+1") instead of following it to the bill or the request path; the
opposite error was over-rating a11y on secondary controls. Both are fixed by the trace in
question 1, not by memorizing levels.

Cite: FIRST CVSS v4.0, §2 (Base metrics: exploitability vs impact).

## 2. Upgrade and downgrade rules

**Upgrade:**
- **U1** error-handling issue on a money, auth or persistent-data-write path: one level up
  (X-SEV-05).
- **U2** state shared across requests, users or runs: the correctness issue is C1 (X-SEV-01).
- **U3** data size is user-controlled or grows without bound: the cost is C2 (X-SEV-02).
- **U4** output contains secrets, tokens or PII: debug output is major (X-SEV-07; CWE-532).

**Downgrade one level:**
- **D1** a trusted-user authorization gate is visible in the diff or file as code: a decorator,
  middleware registration, or explicit role check on the path. Comments, docstrings and claims
  about other files are not gates. Authentication that any self-registered user passes is not a
  trust gate.
- **D2** the collection is small and bounded (a constant, an enum, a config list, a hard page cap).
- **D3** the code is test, fixture or local-script code, and the issue is a runtime problem of
  that code itself (a fixed port, a debug print), not a leaked secret. D3 does not apply to a
  defect that weakens what the suite verifies (a committed `.only`, an assertion that cannot
  fail, a skipped test of changed logic): those are rated on the coverage they remove
  (`refs/tests.md`), with reachability taken from the code under test, so a skipped test of an
  endpoint behind a visible role check is C2 x R2 (D1): minor.
- **D4** the tool autofixes it: nit.

Never apply D1–D3 to the X-SEV-04 classes.

## 3. Confidence, questions and pre-existing issues

| Confidence | Test | Treatment |
|---|---|---|
| high | the quoted lines alone prove it | finding |
| medium | proof needs one assumption; state it in `why` ("assuming `name` comes from the request, as line 157 shows") | finding |
| low | depends on code you have not seen | blocker/major → **question**; minor/nit → **drop** |

- A question names the line, the assumption and the consequence if it holds: "`jobs.py:88` — is
  `retry()` called concurrently? If so, the counter update loses increments."
- Questions do not count in `summary` and do not change the verdict. Absence-of-control items
  (X-SEV-09) are questions at most.
- **Pre-existing** (diff scope only): a blocker on lines the diff does not change and does not
  make newly reachable. Set `"pre_existing": true`, list it under "Pre-existing", exclude it from
  `summary` and the verdict. Any other pre-existing issue is not reported.

Cite: Conventional Comments ("question" label); Google Engineering Practices, "How to write code
review comments".

## 4. Worked examples per level

| # | Example | Consequence / reachability | Level | Anchor |
|---|---|---|---|---|
| B1 | Mutable default list aliased into each request's cart, appended to | C1 data corruption / R1 default path | blocker | X-SEV-01 |
| B2 | `send_file(os.path.join(DIR, request.args["f"]))`, no role check in code | C1 arbitrary file read / R1 | blocker | X-SEV-03 |
| B3 | `if (!canEdit(user, doc))` where `canEdit` is async | C1 authz bypass / R1 | blocker | X-SEV-04 |
| B4 | `<div dangerouslySetInnerHTML={{ __html: comment.text }} />` | C1 stored XSS / R1 | blocker | X-SEV-04 |
| M1 | One query per order inside a request handler, orders unbounded | C2 latency / R1 | major | X-SEV-02 |
| M2 | `except Exception: pass` around a ledger write | C3 swallowed error / R1, raised by U1 (ledger write) | major | X-SEV-05 |
| M3 | Same traversal as B2 behind `@require_role("admin")` | C1 / R2 (D1) | major | X-SEV-03 |
| M4 | 500 response returns `err.stack` | C2 information exposure (CWE-209) / R1 | major | — |
| M5 | `<div onClick={placeOrder}>` is the only way to check out | C2 blocks a core flow / R1 | major | X-SEV-06 |
| m1 | Per-item query over the 3 plan tiers in a config constant | C2 / R2 (D2) | minor | X-SEV-02 |
| m2 | `except Exception: pass` around best-effort cache warm-up | C3 | minor | X-SEV-05 |
| m3 | `print("loaded", order_id)` in a request handler | C3 / R1 | minor | X-SEV-07 |
| m4 | Clickable `<div>` for a secondary "Translate" toggle | C3 / R1 | minor | X-SEV-06 |
| n1 | `import json` unused | C4 | nit | X-SEV-08 |
| n2 | `// const token = sign(...)` commented-out line | C4 | nit | X-SEV-08 |
| n3 | `status == 'disabled'` where `status` is always a string or null | C4 | nit | X-SEV-08 |
| n4 | `print()` left in a one-off migration script | C3 / R3 | nit | X-SEV-07 |

## 5. Calibration anchors

Each anchor fixes the **severity** of a pattern. Detection detail for each pattern belongs to the
topic and language refs; these entries only settle the level.

### X-SEV-01 — Shared mutable state across calls
- **Detect:** mutable default argument (`= []`, `= {}`, `= set()`), class-level mutable
  attribute, or module-level `dict`/`list`/`Map` that a function mutates or returns by
  reference. Trace: does the shared object escape into a result that outlives the call?
- **Default severity:** blocker when it leaks across requests, users or billing runs (data
  corruption on a common path); major when the sharing stays inside one process run or job and
  causes wrong later results there; minor when it is never mutated and never escapes (latent).
- **Why:** the default is evaluated once at definition time, so every call that omits the
  argument shares one object.
- WRONG:
  ```python
  def open_cart(user_id: int, items: list[Item] = []) -> Cart:
      cart = Cart(user_id, items=items)      # every default call shares this list
      cart.items.append(welcome_gift(user_id))
      return cart
  ```
- CORRECT:
  ```python
  def open_cart(user_id: int, items: list[Item] | None = None) -> Cart:
      cart = Cart(user_id, items=list(items or []))
      cart.items.append(welcome_gift(user_id))
      return cart
  ```
- **Fix:** default to `None` and build a new object per call; copy inputs you store.
- **Cite:** Python Tutorial, "Default Argument Values" (important warning); Python Programming
  FAQ, "Why are default values shared between objects?"; CWE-488 when data crosses users.
- **Tool code:** `[ruff: B006]`, `[ruff: RUF012]`.

### X-SEV-02 — Query or remote call per item
- **Detect:** `execute`/`query`/ORM attribute access, `fetch`, `requests.*` or `await` inside a
  loop over rows or API results.
- **Default severity:** major on a request path or over data whose size is user-controlled or
  grows (rows per customer, reviews per product); minor over a small bounded collection (D2).
- **Why:** cost and latency grow linearly with data the author does not control; sequential
  `await` adds every round trip.
- WRONG:
  ```ts
  for (const id of commentIds) {
    const res = await fetch(`/api/users/${id}`);   // one round trip per comment
    authors.push(await res.json());
  }
  ```
- CORRECT:
  ```ts
  const res = await fetch(`/api/users?ids=${commentIds.map(encodeURIComponent).join(',')}`);
  const authors: Author[] = await res.json();    // one batched request
  ```
  ```python
  rows = conn.execute(
      "SELECT o.id, i.sku, i.qty FROM orders o JOIN order_items i ON i.order_id = o.id"
      " WHERE o.customer_id = ?", (customer_id,),
  ).fetchall()                                   # one query instead of one per order
  ```
- **Fix:** JOIN or `IN (...)`, eager loading (`selectinload`, `prefetch_related`), a batch
  endpoint, or `Promise.all` when the calls are independent and the count is bounded.
- **Cite:** CWE-1073; Django docs, "Database access optimization"; SQLAlchemy docs,
  "Relationship Loading Techniques"; web.dev, "Avoid chaining critical requests".
- **Tool code:** none.

### X-SEV-03 — Path traversal / arbitrary file read
- **Detect:** a request-derived value reaches `open`, `send_file`, `os.path.join`,
  `Path(...) /`, `fs.readFile`, `createReadStream` or `res.sendFile` without `resolve()` plus a
  containment check. Suffix checks (`.endswith(".csv")`) do not contain a path.
- **Default severity:** blocker when any caller can reach it; major only when a trusted-user
  authorization gate is visible in the diff or file as code (D1). A docstring saying "the app
  authenticates every request" is not a visible gate.
- **Why:** `../` segments or an absolute path (which `os.path.join` lets replace the base) read
  any file the process can, including secrets and config.
- WRONG:
  ```python
  @bp.get("/reports")
  def report() -> ResponseReturnValue:
      return send_file(os.path.join(REPORT_DIR, request.args["name"]))
  ```
- CORRECT:
  ```python
  @bp.get("/reports")
  def report() -> ResponseReturnValue:
      return send_from_directory(REPORT_DIR, request.args["name"])  # safe_join; 404 on escape
  ```
- **Fix:** Flask `send_from_directory`; otherwise `p = (base / name).resolve()` then
  `p.is_relative_to(base.resolve())`; Express `res.sendFile(name, { root: dir })`.
- **Cite:** CWE-22; OWASP A01:2021 Broken Access Control; Flask docs, `send_from_directory`;
  Python docs, `PurePath.is_relative_to`.
- **Tool code:** none reliable (semgrep `path-traversal` rules if available).

### X-SEV-04 — Always-blocker security classes
- **Detect / WRONG → CORRECT:**

  | Class | WRONG | CORRECT | Cite |
  |---|---|---|---|
  | hardcoded production secret | `API_TOKEN = "prod-9f2c41e7"` | `API_TOKEN = os.environ["API_TOKEN"]` | CWE-798; OWASP A07:2021 |
  | SQL injection | ``db.query(`… WHERE name = '${q}'`)`` | `db.query('… WHERE name = $1', [q])` | CWE-89; OWASP A03:2021 |
  | missing `await` on an auth check | `if (!canEdit(user, doc)) return deny();` | `if (!(await canEdit(user, doc))) return deny();` | CWE-287 / CWE-285; ECMA-262 ToBoolean (a Promise is truthy) |
  | XSS from user text | `<p dangerouslySetInnerHTML={{ __html: c.text }} />` | `<p>{c.text}</p>` (or sanitize with DOMPurify when HTML is required) | CWE-79; OWASP A03:2021; React docs, `dangerouslySetInnerHTML` |

- **Default severity:** blocker. Not downgraded by D1–D3: a secret in a test file or behind a
  login is still leaked; injection behind authentication that anyone can sign up for is still
  open. A secret embedded in a client bundle is also exposed to every visitor (CWE-200).
- **Why:** each gives an attacker accounts, data or code execution with no precondition beyond
  reaching the line.
- **Fix:** environment or secret manager and rotate the leaked value; bound parameters; `await`
  the check (and enable `no-misused-promises`); render as text.
- **Tool code:** `[ruff: S105, S106, S608]`, `[typescript-eslint: no-misused-promises,
  no-floating-promises]`, `[eslint-plugin-react: no-danger]`, secret scanners (gitleaks).

### X-SEV-05 — Swallowed exception
- **Detect:** `except …: pass`, `except Exception` that only returns a default, empty
  `catch {}`, `.catch(() => {})`, or a catch that drops the error without logging or re-raising.
- **Default severity:** major on a money or data-write path (U1); minor elsewhere (best-effort
  cache, telemetry, optional enrichment).
- **Why:** the failure disappears; on a charge or write path it becomes a wrong balance or a
  lost record that nobody sees.
- WRONG:
  ```python
  try:
      ledger.post(entry)
  except Exception:
      pass
  ```
- CORRECT:
  ```python
  try:
      ledger.post(entry)
  except LedgerError:
      logger.exception("ledger post failed for entry %s", entry.id)
      raise
  ```
- **Fix:** catch the specific exception, log with context, re-raise or return an explicit
  failure the caller must handle; chain with `raise … from err`.
- **Cite:** CWE-390; CWE-396; PEP 8, "Programming Recommendations" (bare `except`).
- **Tool code:** `[ruff: S110, BLE001, E722]`, `[eslint: no-empty]`, `[mypy: return]` when the
  swallow leaves a path with no return.

### X-SEV-06 — Clickable element without keyboard access
- **Detect:** `onClick` on `div`/`span`/`li` with no `role`, `tabIndex` and key handler.
- **Default severity:** minor for one secondary control (a toggle, an optional action); major
  when it is the only way through a core flow (checkout, login, submit, primary navigation,
  closing a modal).
- **Why:** keyboard and many screen-reader users cannot reach or activate it (a WCAG Level A
  failure); the user's loss is the flow behind it, which sets the level.
- WRONG:
  ```tsx
  <div className="filters__toggle" onClick={() => setOpen(!open)}>Filters</div>
  ```
- CORRECT:
  ```tsx
  <button type="button" className="filters__toggle" aria-expanded={open}
          onClick={() => setOpen(!open)}>Filters</button>
  ```
- **Fix:** use a native `<button>` or `<a href>`.
- **Cite:** WCAG 2.2 SC 2.1.1 Keyboard (Level A); WAI-ARIA APG, "Button pattern".
- **Tool code:** `[jsx-a11y: click-events-have-key-events, no-static-element-interactions]`.

### X-SEV-07 — Debug output left in code
- **Detect:** `print(`, `console.log(`, `pprint`, `debugger`, `breakpoint()`.
- **Default severity:** nit by default (scripts, CLIs, tests); minor on a request path or code that
  runs on every page load; major when it logs secrets, tokens, passwords or PII (U4).
- **Why:** bypasses the structured logger and its redaction; on a request path it is
  unfiltered, unleveled output in production.
- WRONG:
  ```js
  console.log('session', req.session.token);       // major: token in logs
  ```
- CORRECT:
  ```js
  req.log.debug({ userId: req.user.id }, 'session restored');
  ```
- **Fix:** delete it, or replace it with the project logger at `debug` level without secrets.
- **Cite:** CWE-532; OWASP Logging Cheat Sheet.
- **Tool code:** `[ruff: T201, T203]`, `[eslint: no-console, no-debugger]`.

### X-SEV-08 — Hygiene with no runtime effect
- **Detect:** unused import or variable; commented-out code; `==`/`!=` where both operands
  always have the same type (string field vs string literal, or `null`).
- **Default severity:** nit. Loose equality becomes a correctness finding (minor or major by
  consequence) when coercion can change the result: number vs string, user input, `0`, `''`,
  `[]`.
- **Why:** reader cost only; the tool usually autofixes it.
- WRONG:
  ```js
  import { useMemo, useState } from 'react';   // useMemo unused
  // const legacy = await oldClient.get(id);
  if (order.state == 'paid') { … }            // state is a string column
  ```
- CORRECT:
  ```js
  import { useState } from 'react';
  if (order.state === 'paid') { … }
  ```
- **Fix:** remove or autofix; version control keeps the old code.
- **Cite:** PEP 8 (imports); ECMA-262 `IsLooselyEqual`; SonarSource rule S125 (commented-out
  code).
- **Tool code:** `[ruff: F401, ERA001]`, `[tsc: TS6133]`, `[eslint: no-unused-vars, eqeqeq]`.

### X-SEV-09 — Hardening not present in the diff
- **Detect:** a candidate finding whose evidence would be the *absence* of a control: rate
  limiting, security headers (helmet), a JWT `algorithms` allowlist, constant-time comparison or
  timing equalization.
- **Default severity:** no finding. If the diff adds or changes the code that would hold the
  control, one question at most. If the code shown makes a concrete attack work, it is a
  security finding rated by §1 (e.g. `jwt.verify(token, publicKey)` with no `algorithms` on a
  library version that accepts HS256: algorithm confusion, CWE-347).
- **Why:** these controls often live in a gateway, proxy, plugin file or library default the
  diff does not show. Reporting their absence as findings is the main source of baseline noise.
- WRONG:
  ```text
  [minor] app.mjs:14 NODE-SEC-09: No helmet registered on the app
  ```
- CORRECT:
  ```text
  Questions:
  - app.mjs:75 — The diff adds /login. Is it rate-limited at the gateway? If not, it is open to
    credential stuffing (OWASP ASVS V2.2.1).
  ```
- **Fix:** none required in the report.
- **Cite:** OWASP ASVS 4.0.3 V2.2.1 (anti-automation); RFC 8725 §3.1 (perform algorithm
  verification); CWE-208.
- **Tool code:** none.

## 6. Noise suppression

Unseeded findings the no-skill baseline produced, with the rule for each.

| Finding seen | Report when | Do not report when | Cite |
|---|---|---|---|
| No rate limiting on login | question only: the diff adds or changes a credential endpoint and nothing shown applies a limit | always as a finding; when the diff does not touch the route | OWASP ASVS V2.2.1 |
| No helmet / security headers | question only: the diff builds the app's plugin chain for a service that serves HTML | JSON-only APIs; diffs that do not touch app setup | OWASP Secure Headers Project |
| JWT algorithm not pinned | finding only when the shown code allows algorithm confusion or `none`; else a question when the diff adds the verify call | the verify call is unchanged; symmetric secret with a library that rejects `none` | RFC 8725 §2.1, §3.1; CWE-347 |
| Timing-based user enumeration (early return before the hash) | question when the diff changes the login comparison | as a finding; when login is untouched | CWE-208 |
| Signup 409 "email already registered" | login or password reset distinguishes "unknown account" from "wrong password" (minor, CWE-204) | signup itself: registration reveals existence unless the product uses an emailed-link flow, a product decision | OWASP Authentication Cheat Sheet, "Authentication and error messages" |
| Shutdown handler without try/catch | the handler can hang with no exit path (minor) | a rejection in the handler crashes the process with a non-zero exit, which is the handler's goal (Node ≥ 15 default `--unhandled-rejections=throw`) | Node.js docs, `process` "unhandledRejection" |
| `aria-label` on a role-less `<span>` | nit, fix `role="img"`; minor when the visible content conveys nothing (an icon glyph with no text) | visible text already carries the meaning | WAI-ARIA 1.2 (naming prohibited on `generic`) |
| Derived file written after the DB commit | a side effect that cannot be replayed (charge, email, event) happens outside the transaction with no record: major, use an outbox | the artifact can be regenerated from committed data (commit first, derive after is correct) | microservices.io, "Transactional outbox" |

Real unseeded issues are **not** noise and stay reportable: a charge sent without an idempotency
key, an effect without cleanup or `AbortController`, a cache key missing a dimension. The rule
above targets low-value and absence-of-control items only.

## 7. Output format: Markdown and JSON

Write both on every run. The Markdown follows `tooling/report-template.md`; the JSON validates
against `tooling/finding.schema.json`. The two carry the same findings, sort order and counts.

**Field rules**
- `file`: path relative to the repository root (or as given, in file scope).
- `line`: first line of `evidence` in the new or working-tree file.
- `evidence`: verbatim (common indentation may be removed), at most 5 lines, joined with `\n`;
  quote removed lines with their `-`.
- `title`: ≤ 120 characters, states the defect, not the fix.
- `why`: consequence and reachability (§1), plus any medium-confidence assumption.
- `fix`: a suggestion or a small diff; never a full rewrite.
- `cite`: the standard named by the rule (CWE, OWASP, PEP, RFC, WCAG, official doc).
- `source` / `tool_code`: the tool when a tool reported it, else `model`.
- Sort: severity (blocker → nit), then file, then line.

**Markdown example (one blocker)**

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

**JSON example (same finding, full report)**

```json
{
  "verdict": "request changes",
  "mode": "full",
  "scope": {"kind": "diff", "base": "main", "files": ["src/routes/orders.mjs"], "languages": ["node"]},
  "tools": [{"name": "eslint", "status": "ran", "note": "project config eslint.config.js"}],
  "findings": [
    {
      "severity": "blocker",
      "confidence": "high",
      "file": "src/routes/orders.mjs",
      "line": 27,
      "rule_id": "NODE-SEC-01",
      "title": "Order id from the URL concatenated into SQL",
      "evidence": "const { rows } = await db.query(`SELECT * FROM orders WHERE id = ${req.params.id}`);",
      "why": "req.params.id reaches the SQL text on GET /orders/:id, which any logged-in customer can call (signup is open), so 1 OR 1=1 returns every customer's orders.",
      "fix": "await db.query('SELECT * FROM orders WHERE id = $1 AND customer_id = $2', [req.params.id, req.user.id])",
      "cite": "CWE-89; OWASP A03:2021 Injection",
      "source": "model"
    }
  ],
  "questions": [],
  "summary": {"blocker": 1, "major": 0, "minor": 0, "nit": 0}
}
```

## 8. Nits: collapsing and the cap

- **Markdown:** linter-reported nits collapse to one line per tool, with the codes and the
  autofix command (`7 nits from ruff (E501, I001): run ruff check --fix`). Model nits: list at most
  5, most useful first; drop the rest.
- **JSON:** every linter nit is listed (tool-sourced, cheap to filter); model nits are capped at
  5, the same ones the Markdown lists.
- `summary.nit` counts the nit findings in the JSON, so the Markdown table and the JSON agree.
- A review with only nits states so in one line; it does not pad with minor findings.

Cite: Google Engineering Practices, "How to write code review comments" ("Nit:" prefix for
optional polish).

## 9. Verdict rules

Computed from findings with `pre_existing` false; questions never change it.

| Highest severity | Verdict |
|---|---|
| any blocker or major | **request changes** |
| only minor and/or nit | **approve with nits** |
| no findings | **approve** |

If pre-existing blockers exist, the verdict line adds them: `approve — 1 pre-existing blocker
needs a separate fix`. The schema rejects a verdict that does not match `summary`.

Cite: Google Engineering Practices, "The Standard of Code Review".
