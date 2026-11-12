# Auditline report

**Scope:** file `module_a.mjs`, `module_b.mjs`, `module_c.mjs`, `module_e.mjs`, `module_e.test.mjs` (no git context; whole files in scope) · **Mode:** full · **Languages:** node
**Tools:** eslint: ran (bundled fallback config; 4 results dropped, see JSON `tools` note) | tsc: skipped (no tsconfig.json)
**Coverage:** all files in scope

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 7 | 8 | 1 | 4 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

`module_a.mjs` and `module_b.mjs`: no findings.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.mjs:10` NODE-SEC-02: JWT signing key hardcoded in source

```js
const JWT_SECRET = 'c0mmunity-jwt-s1gning-k3y-2024';
```

**Why:** Consequence: the HS256 key that signs and verifies every session token is in the repository, so anyone with the code, an image or git history can mint a token with any sub and role (e.g. role 'admin'). Reachability: the leak happens at commit; X-SEV-04, never downgraded.
**Fix:** Read it from the environment and fail fast when unset (`const JWT_SECRET = requireEnv('JWT_SECRET')`), and rotate the leaked key; every token signed with it must be treated as compromised.
**Cite:** CWE-798; OWASP A07:2021 Identification and Authentication Failures; OWASP Secrets Management Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_c.mjs:85` NODE-SEC-20: bcrypt.compare not awaited: any password logs in

```js
const valid = bcrypt.compare(password, user.password_hash);
```

**Why:** Consequence: bcrypt.compare returns a Promise, which is always truthy, so `!valid` is never true and POST /login issues a token for any known email with any password (account takeover). Reachability: anonymous, every login request (R1). X-SEV-04 class.
**Fix:** `const valid = await bcrypt.compare(password, user.password_hash);` and enable typescript-eslint `no-misused-promises` to catch it.
**Cite:** CWE-287; OWASP A07:2021 Identification and Authentication Failures; ECMA-262 ToBoolean (objects are truthy); bcrypt README (compare returns a Promise without a callback)
**Source:** model · confidence: high

### [blocker] `module_c.mjs:104` NODE-SEC-01: Search term q interpolated into the SQL text

```js
WHERE status = 'active' AND display_name ILIKE '%${q}%'
```

**Why:** Consequence: q from the query string becomes SQL syntax, so `q=x' OR '1'='1' --` or a UNION SELECT reads any column of users (password_hash, email, role) or other tables; maxLength 64 does not neutralise injection. Reachability: GET /members/search only needs a token, and POST /signup issues one to anyone, so it is open (R1); X-SEV-04, never downgraded by a login anyone can pass.
**Fix:** Bind it: `... AND display_name ILIKE $1 ... LIMIT $2` with `[`%${q.replace(/[\\%_]/g, '\\$&')}%`, limit]` (escape LIKE wildcards in the bound value).
**Cite:** CWE-89; OWASP A03:2021 Injection; node-postgres docs, "Queries" (parameterized query)
**Source:** model · confidence: high

### [blocker] `module_e.mjs:49` NODE-COR-09: Lost update: subtotal += await inside Promise.all keeps only one meter

```js
subtotalCents += await meterChargeCents(teamId, meter, start, end);
```

**Why:** Consequence: `subtotalCents += await x` reads subtotalCents (0) before the await in all three callbacks, so the result is the last meter to resolve, not the sum: meters of 1000, 1000 and 1000 cents give 1000, not 3000. The wrong subtotal and amountDue are inserted into invoices and billed. Reachability: every invoice for every team on the default path of POST /api/admin/teams/:teamId/invoices; the admin gate limits who issues invoices, not whose bill is wrong (C1 money).
**Fix:** Collect then combine: `const parts = await Promise.all(METERS.map((m) => meterChargeCents(teamId, m, start, end))); const subtotalCents = parts.reduce((a, b) => a + b, 0);`
**Cite:** CWE-362; ESLint docs, require-atomic-updates; ECMA-262 compound assignment evaluation order
**Source:** eslint (require-atomic-updates) · confidence: high

### [blocker] `module_e.mjs:52` NODE-COR-08: Invoice amount due computed and stored as a float in dollars

```js
const amountDue = Math.round((subtotalCents / 100) * (1 + TAX_RATE) * 100) / 100;
```

**Why:** Consequence: `(cents / 100) * 1.0825 * 100` is binary floating point, so a subtotal of 6200 cents gives 6711.499999999999 and rounds to 67.11 instead of 67.12; the float amountDue is inserted into invoices.amount_due and returned to the client. Reachability: every invoice whose taxed total lands on a half cent (C1 money stored in the ledger).
**Fix:** Integer cents end to end: `const amountDueCents = Math.round(subtotalCents * 10825 / 10000)` (or a decimal library with an explicit rounding mode) and store amount_due_cents as an integer/numeric column.
**Cite:** CWE-682; CWE-1339; ECMA-262 Number type (IEEE 754 binary64)
**Source:** model · confidence: high

### [blocker] `module_e.mjs:84` NODE-SEC-04: Admin usage route registered before authenticate and requireRole: open to anyone

```js
app.get('/api/admin/teams/:teamId/usage', asyncHandler(async (req, res) => {
```

**Why:** Consequence: Express runs middleware in registration order; this route is declared above `app.use('/api', authenticate)` (line 92) and `app.use('/api/admin', requireRole('admin'))` (line 93), so neither runs and any anonymous caller reads any team's usage by UUID. Reachability: anonymous, R1. Authorization bypass, X-SEV-04 (the test at module_e.test.mjs:47 expects 403).
**Fix:** Move the route below the two `app.use` lines (register auth middleware before every /api route), or attach the guards on the route: `app.get('/api/admin/teams/:teamId/usage', authenticate, requireRole('admin'), asyncHandler(...))`.
**Cite:** CWE-862; OWASP A01:2021 Broken Access Control; Express docs, "Using middleware" (order of middleware loading is important)
**Source:** model · confidence: high

### [blocker] `module_e.mjs:123` NODE-SEC-04: Document deleted by id alone, with no ownership check

```js
const { rowCount } = await pool.query('DELETE FROM documents WHERE id = $1', [req.params.id]);
```

**Why:** Consequence: DELETE /api/documents/:id deletes by the client-supplied id while req.user.sub is in scope but not in the query, so any authenticated user deletes any team's document (data loss for other users); the search route on line 107 shows ownership is owner_id. Reachability: any token holder (R1); IDOR is X-SEV-04.
**Fix:** `DELETE FROM documents WHERE id = $1 AND owner_id = $2` with `[req.params.id, req.user.sub]` (or the team/role rule the product uses), and keep the 404 on rowCount 0.
**Cite:** CWE-639; OWASP A01:2021 Broken Access Control; OWASP API Security Top 10 2023 API1 (BOLA)
**Source:** model · confidence: high

### [major] `module_c.mjs:60` NODE-PERF-02: bcrypt.hashSync at cost 12 blocks the event loop on every signup

```js
const passwordHash = bcrypt.hashSync(password, BCRYPT_ROUNDS);
```

**Why:** Consequence: hashSync at 12 rounds holds the single event-loop thread for roughly a quarter second, so every concurrent request waits; a burst of signups stalls the whole service. Reachability: POST /signup is anonymous (R1).
**Fix:** `const passwordHash = await bcrypt.hash(password, BCRYPT_ROUNDS);` (runs on the libuv pool).
**Cite:** Node.js docs, "Don't Block the Event Loop (or the Worker Pool)"; eslint-plugin-n, no-sync
**Source:** eslint (n/no-sync) · confidence: high

### [major] `module_c.mjs:71` NODE-SEC-18: 500 response returns err.message and err.stack to the client

```js
return reply.code(500).send({ error: err.message, stack: err.stack });
```

**Why:** Consequence: any database error on signup (connection failure, constraint names, SQL text) is sent to the caller with the stack trace, revealing file paths, library versions and schema, and the error is never logged server-side. Reachability: anonymous POST /signup (R1); severity ref M4.
**Fix:** Log it (`request.log.error({ err }, 'signup failed')`) and rethrow so Fastify returns a generic 500, or send `{ type: 'about:blank', title: 'Internal Server Error', status: 500 }` as application/problem+json.
**Cite:** CWE-209; OWASP A05:2021 Security Misconfiguration; OWASP Error Handling Cheat Sheet; RFC 9457
**Source:** model · confidence: high

### [major] `module_e.mjs:67` NODE-COR-10: return mailer.sendMail() inside try without await: the catch never runs

```js
return mailer.sendMail({
```

**Why:** Consequence: sendMail returns a Promise; returning it un-awaited leaves the try before it settles, so an SMTP rejection skips the catch, the 'quota warning not delivered' log never happens, and the function rejects instead of returning null. The quota-warning route then answers 500 instead of `{ sent: false }` (the test at module_e.test.mjs:73 expects null). Reachability: every SMTP failure on POST /api/admin/teams/:teamId/quota-warning.
**Fix:** `return await mailer.sendMail({ ... });` (typescript-eslint `return-await: in-try-catch`).
**Cite:** ECMA-262 async function return semantics; MDN, "await"; CWE-252; typescript-eslint, return-await
**Source:** model · confidence: high

### [major] `module_e.mjs:100` NODE-ERR-06: Pooled client released only on success: every search error leaks a connection

```js
const client = await pool.connect();
```

**Why:** Consequence: `client.release()` (line 112) is inside the try, so when a query throws, including the expected statement-timeout path (57014 → 503), the client is never returned. node-postgres pools default to 10 clients, so ten slow or failing searches exhaust the pool and every route that uses `pool` hangs. Reachability: any authenticated user can send a broad query that times out (R1).
**Fix:** Release in `finally` (and pass the error to `release(err)` when the session state is unknown): `try { ... } catch (err) { ... } finally { client.release(); }`; or use `SET LOCAL statement_timeout` inside a transaction so no RESET is needed.
**Cite:** CWE-772; CWE-404; node-postgres docs, "Pooling" (a checked-out client must be released)
**Source:** model · confidence: high

### [major] `module_e.mjs:141` NODE-COR-07: Invoice due date via setUTCMonth(+1) overflows at month end

```js
dueAt.setUTCMonth(dueAt.getUTCMonth() + 1);
```

**Why:** Consequence: an invoice issued on 2026-01-31 gets dueAt 2026-03-03 (Feb 31 rolls over), and the 29th-31st of short months all skip a month; the wrong due date is stored in invoices.due_at and drives payment terms. Reachability: every invoice issued on those days (stored, billed value).
**Fix:** Clamp to the last day of the next month: `const y = issuedAt.getUTCFullYear(), m = issuedAt.getUTCMonth() + 1; const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate(); dueAt = new Date(Date.UTC(y, m, Math.min(issuedAt.getUTCDate(), last)));` or a date library's addMonths.
**Cite:** CWE-682; ECMA-262, Date.prototype.setUTCMonth (MakeDay overflow); MDN, Date.prototype.setUTCMonth
**Source:** model · confidence: high

### [major] `module_e.test.mjs:43` NODE-TEST-02: Wrong-key test asserts only inside a catch that fetch never reaches

```js
expect(err.status).toBe(401);
```

**Why:** Consequence: fetch resolves on a 401 (it rejects only on network errors), so the catch never runs and the test passes whatever the server does; a server that accepts tokens signed with another key would still be green. It is the only test of signature rejection (auth logic).
**Fix:** `const response = await fetch(`${BASE_URL}/api/documents/${DOC_ID}`, { method: 'DELETE', headers }); expect(response.status).toBe(401);`
**Cite:** Jest docs, "Testing Asynchronous Code"; eslint-plugin-jest, no-conditional-expect; WHATWG Fetch Standard (the promise rejects only on network errors)
**Source:** model · confidence: high

### [major] `module_e.test.mjs:55` NODE-TEST-06: it.only committed: Jest skips every other test in the file

```js
it.only('adds up every meter before tax', async () => {
```

**Why:** Consequence: with `.only`, Jest runs this one test and reports the file green, so the auth tests, the rounding test, the failure-propagation test and the quota-warning test never run (and the last one would fail today, see module_e.mjs:67). This test itself fails against the current computeInvoice (1000, not 3000).
**Fix:** Remove `.only`; add eslint-plugin-jest `no-focused-tests` to CI.
**Cite:** Jest docs, test.only; eslint-plugin-jest, no-focused-tests
**Source:** model · confidence: high

### [major] `module_e.test.mjs:63` NODE-TEST-02: .resolves assertion neither awaited nor returned

```js
expect(computeInvoice(TEAM_ID, ...PERIOD)).resolves.toMatchObject({ amountDue: 64.95 });
```

**Why:** Consequence: the test is synchronous and does not return the expect, so it ends before the promise settles and passes whatever amountDue is; a mismatch surfaces at best as an unhandled rejection outside the test. It is the only test of the taxed-total rounding (money).
**Fix:** Make it `async` and `await expect(computeInvoice(TEAM_ID, ...PERIOD)).resolves.toMatchObject({ amountDue: 64.95 });`, and add a half-cent case (subtotal 6200 cents → 67.12).
**Cite:** Jest docs, ".resolves" (return or await the assertion); eslint-plugin-jest, valid-expect
**Source:** model · confidence: high

### [minor] `module_c.mjs:89` NODE-DIFF-01: console.log left in the login handler

```js
console.log('login user', user.id, user.status);
```

**Why:** Consequence: every successful password check writes unstructured stdout outside the Fastify logger (no level, no request id, no redaction). Reachability: every login request (R1); user id and status are identifiers, not secrets, so minor (X-SEV-07).
**Fix:** Delete it, or `request.log.info({ userId: user.id }, 'login succeeded')`.
**Cite:** CWE-532; OWASP Logging Cheat Sheet; ESLint docs, no-console
**Source:** eslint (no-console) · confidence: high

### [nit] `module_c.mjs:93` X-DIFF-02: Commented-out token signing code

```js
// const token = jwt.sign({ id: user.id }, JWT_SECRET, { expiresIn: '7d' });
```

**Why:** A disabled jwt.sign with a 7-day expiry; readers cannot tell whether it is a plan or a leftover, and version control keeps it (X-SEV-08 n2).
**Fix:** Delete the line.
**Cite:** Martin, Clean Code ch. 4, "Commented-Out Code"; SonarSource rule S125
**Source:** model · confidence: high

### [nit] `module_e.test.mjs:21` NODE-TEST-05: Test server bound to a fixed port 4100

```js
server = app.listen(4100);
```

**Why:** A fixed port collides with another process or a parallel Jest worker and fails the suite with EADDRINUSE; test-code runtime issue, so D3 applies.
**Fix:** `server = app.listen(0); await once(server, 'listening'); const BASE_URL = `http://127.0.0.1:${server.address().port}`;`
**Cite:** Martin Fowler, "Eradicating Non-Determinism in Tests"; Node.js docs, server.listen (port 0 assigns a free port)
**Source:** model · confidence: medium

### [nit] 2 nits from eslint

Collapsed because eslint reports them (eqeqeq, no-unused-vars) at `module_c.mjs:90`, `module_e.mjs:7`. Run `npx eslint --fix`.

## Questions

Low-confidence blockers or majors, and absence-of-control items, go here, not above. Questions do not change the verdict.

- `module_c.mjs:82` — Login returns before any bcrypt work when the email is unknown, and runs a cost-12 compare when it is known (once the await is fixed). Is response timing on /login monitored or equalized elsewhere? If not, response time reveals which emails have accounts (CWE-208); compare against a dummy hash for unknown users.

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
