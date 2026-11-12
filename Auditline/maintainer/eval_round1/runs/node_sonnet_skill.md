# Auditline report

**Scope:** file `module_a.mjs`, `module_b.mjs`, `module_c.mjs`, `module_e.mjs`, `module_e.test.mjs` · **Mode:** full · **Languages:** node
**Tools:** eslint: ran (bundled fallback config) | tsc: skipped (no tsconfig.json)
**Coverage:** all files in scope. `module_a.mjs` and `module_b.mjs`: no findings.

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 5 | 8 | 3 | 4 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.mjs:10` NODE-SEC-02: JWT signing key hardcoded in source

```js
const JWT_SECRET = 'c0mmunity-jwt-s1gning-k3y-2024';
```

**Why:** The key that signs every session token is a literal in the file, so anyone with the repository, an image or a log of it can mint a token with any `sub` and `role`; the leak happens at commit, so reachability does not matter (X-SEV-04).
**Fix:** const JWT_SECRET = process.env.JWT_SECRET; if (!JWT_SECRET) throw new Error('JWT_SECRET is not set'); and rotate the leaked value.
**Cite:** CWE-798; OWASP A07:2021 Identification and Authentication Failures; OWASP Secrets Management Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_c.mjs:85` NODE-SEC-20: bcrypt.compare result not awaited: login accepts any password

```js
const valid = bcrypt.compare(password, user.password_hash);
```

**Why:** `bcrypt.compare` returns a Promise, which is always truthy, so `!valid` is never true and every request that names an existing email gets a token. Any anonymous caller can sign in as any user (C1 auth bypass, R1: /login is open).
**Fix:** const valid = await bcrypt.compare(password, user.password_hash);
**Cite:** CWE-287; OWASP A07:2021; ECMA-262 ToBoolean (a Promise is truthy); bcrypt README (compare is async)
**Source:** model · confidence: high

### [blocker] `module_c.mjs:104` NODE-SEC-01: Search term interpolated into SQL text

```js
WHERE status = 'active' AND display_name ILIKE '%${q}%'
```

**Why:** `q` comes from the query string and is placed inside the SQL string; schema `maxLength: 64` does not neutralise injection. Any self-registered user (signup is open) can send `%' OR ...` / UNION payloads and read or change any table the role can reach (C1/R1).
**Fix:** WHERE status = 'active' AND display_name ILIKE $1 ... [`%${q.replace(/[\\%_]/g, '\\$&')}%`, limit]
**Cite:** CWE-89; OWASP A03:2021 Injection; OWASP SQL Injection Prevention Cheat Sheet; node-postgres docs, Queries (parameterized query)
**Source:** model · confidence: high

### [blocker] `module_e.mjs:84` NODE-SEC-04: Admin usage route registered before the auth and role middleware

```js
app.get('/api/admin/teams/:teamId/usage', asyncHandler(async (req, res) => {
```

**Why:** Express runs middleware in registration order. This route sits above `app.use('/api', authenticate)` (line 92) and `app.use('/api/admin', requireRole('admin'))` (line 93), so GET /api/admin/teams/:teamId/usage answers anonymous callers with any team's usage data (C1 broken access control / R1). The sibling admin routes below the guards are protected; this one is not.
**Fix:** Move the app.get('/api/admin/teams/:teamId/usage', ...) registration below the two app.use guards (and add a team-membership check if admins are per team).
**Cite:** CWE-862; OWASP A01:2021 Broken Access Control; Express docs, Using middleware (order of middleware loading is important)
**Source:** model · confidence: high

### [blocker] `module_e.mjs:123` NODE-SEC-04: Document deleted by id with no ownership check

```js
const { rowCount } = await pool.query('DELETE FROM documents WHERE id = $1', [req.params.id]);
```

**Why:** Any authenticated user can DELETE /api/documents/:id for a document they neither own nor share: the query filters on the id alone, while the search route above scopes by `owner_id`/share. UUIDs are not authorization (C1 other users' data destroyed / R1).
**Fix:** await pool.query('DELETE FROM documents WHERE id = $1 AND owner_id = $2', [req.params.id, req.user.sub]); return 404 on rowCount 0.
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; OWASP IDOR Prevention Cheat Sheet
**Source:** model · confidence: high

### [major] `module_c.mjs:60` NODE-PERF-02: bcrypt.hashSync blocks the event loop on signup

```js
const passwordHash = bcrypt.hashSync(password, BCRYPT_ROUNDS);
```

**Why:** A cost-12 hash takes on the order of 100-250 ms of synchronous CPU; /signup is open to anyone, so a handful of concurrent requests stalls every other request on the process (C2/R1).
**Fix:** const passwordHash = await bcrypt.hash(password, BCRYPT_ROUNDS);
**Cite:** Node.js docs, "Don't Block the Event Loop (or the Worker Pool)"; bcrypt README (async API)
**Source:** eslint (n/no-sync) · confidence: high

### [major] `module_c.mjs:71` NODE-SEC-18: 500 response returns err.message and err.stack

```js
return reply.code(500).send({ error: err.message, stack: err.stack });
```

**Why:** Any database error other than 23505 (a connection failure, a constraint or syntax error) is sent to the caller with its message and stack trace, exposing table and column names, driver version and file paths to anyone who can reach /signup (C2 information exposure / R1).
**Fix:** req.log.error({ err }, 'signup failed'); return reply.code(500).type('application/problem+json').send({ type: 'about:blank', title: 'Internal Server Error', status: 500 });
**Cite:** CWE-209; OWASP A05:2021 Security Misconfiguration; OWASP Error Handling Cheat Sheet; RFC 9457
**Source:** model · confidence: high

### [major] `module_e.mjs:49` NODE-COR-09: Lost updates: += await inside Promise.all drops all but one meter

```js
subtotalCents += await meterChargeCents(teamId, meter, start, end);
```

**Why:** `subtotalCents` is read before each await, so the three concurrent callbacks each add to 0 and the last write wins. With meter charges 1000, 2000 and 3000 cents the subtotal is whichever resolves last, not 6000; every invoice is under-billed (C1 money wrong / R2: admin-only endpoint, so major).
**Fix:** const parts = await Promise.all(METERS.map((m) => meterChargeCents(teamId, m, start, end))); const subtotalCents = parts.reduce((a, b) => a + b, 0);
**Cite:** CWE-362; CWE-367; ESLint docs, require-atomic-updates
**Source:** eslint (require-atomic-updates) · confidence: high

### [major] `module_e.mjs:52` NODE-COR-08: Invoice total computed with floating point dollars

```js
const amountDue = Math.round((subtotalCents / 100) * (1 + TAX_RATE) * 100) / 100;
```

**Why:** `Math.round((cents / 100) * 1.0825 * 100) / 100` rounds a binary float: for subtotalCents = 6200 the exact taxed total is 67.115 and the code returns 67.11, not 67.12 (checked in Node; 12 of the first 200,000 cent values are off by a cent). The value is stored in invoices.amount_due, and the code mixes cents (subtotalCents) with dollars (amountDue). Admin-gated, so major.
**Fix:** Keep integers: const amountDueCents = Math.round(subtotalCents * 10825 / 10000) (or BigInt/decimal) and store cents.
**Cite:** ECMA-262 Number type (IEEE 754 binary64); Stripe API docs, Currencies (amounts in the smallest unit); CWE-682; CWE-1339
**Source:** model · confidence: high

### [major] `module_e.mjs:112` NODE-ERR-06: Pooled client released only on success: leaked on every error or timeout

```js
client.release();
```

**Why:** `client.release()` follows the queries inside `try` with no `finally`. When the query throws (including the 57014 timeout this route is built to handle) the function returns from the catch and the client is never released, so after pool-size failures every request on the service waits for a connection (C2 outage / R1: any authenticated user hits /api/search).
**Fix:** Wrap in try { ... } finally { client.release(); } and reset statement_timeout with SET LOCAL inside a transaction, or pass the timeout per query.
**Cite:** node-postgres docs, Pooling (a checked-out client must be released); CWE-772; CWE-404
**Source:** model · confidence: high

### [major] `module_e.test.mjs:40` NODE-TEST-02: Wrong-key test asserts only inside a catch that fetch never reaches

```js
try {
  await fetch(`${BASE_URL}/api/documents/${DOC_ID}`, { method: 'DELETE', headers });
} catch (err) {
  expect(err.status).toBe(401);
}
```

**Why:** `fetch` resolves on HTTP 401, it does not throw, so the `catch` block (and its `expect(err.status)`) never runs: the test passes whatever the server does, including accepting the forged token. It is the only test of the invalid-signature path on the DELETE route.
**Fix:** const response = await fetch(url, { method: 'DELETE', headers }); expect(response.status).toBe(401);
**Cite:** Jest docs, Expect (expect.assertions) and Testing Asynchronous Code; WHATWG Fetch Standard (the promise rejects only on network errors)
**Source:** model · confidence: high

### [major] `module_e.test.mjs:55` NODE-TEST-06: it.only narrows the whole file to one test

```js
it.only('adds up every meter before tax', async () => {
```

**Why:** Jest runs only this test; the other six tests in the file, including the authentication, rounding, failure and SMTP tests, are silently skipped while the run reports green. Jest does not reject .only in CI.
**Fix:** Remove .only.
**Cite:** Jest docs, test.only; ESLint plugin jest, no-focused-tests
**Source:** model · confidence: high

### [major] `module_e.test.mjs:63` NODE-TEST-02: Unawaited .resolves assertion in a synchronous test

```js
expect(computeInvoice(TEAM_ID, ...PERIOD)).resolves.toMatchObject({ amountDue: 64.95 });
```

**Why:** The test function is not async and the `expect(...).resolves` promise is neither awaited nor returned, so the test finishes before the assertion runs and passes even if `amountDue` is wrong. It is the only test of the tax rounding (and, with the 64.95 expectation, a float-rounding regression would go unseen).
**Fix:** it('rounds ...', async () => { await expect(computeInvoice(...)).resolves.toMatchObject({ amountDue: 64.95 }); });
**Cite:** Jest docs, .resolves (return or await the assertion)
**Source:** model · confidence: high

### [minor] `module_c.mjs:89` NODE-DIFF-01: console.log left in the login handler

```js
console.log('login user', user.id, user.status);
```

**Why:** Unleveled output on a request path that runs on every login: it bypasses the Fastify logger, its levels and its redaction. It logs only the user id and status, not secrets, so it stays minor (X-SEV-07).
**Fix:** Delete it, or use request.log.debug({ userId: user.id }, 'login') without the status.
**Cite:** CWE-532; CWE-489; OWASP Logging Cheat Sheet
**Source:** eslint (no-console) · confidence: high

### [minor] `module_e.mjs:67` NODE-COR-10: return mailer.sendMail() inside try without await bypasses the catch

```js
return mailer.sendMail({
```

**Why:** The Promise is returned before it settles, so an SMTP rejection skips `catch`: the warning is never logged and the function rejects instead of returning null, which its callers (`info !== null`) and its own test expect. The admin quota-warning route then answers 500 instead of `{ sent: false }`. Admin-gated, so minor (C2/R2).
**Fix:** return await mailer.sendMail({ ... });
**Cite:** ECMA-262 async function return semantics; typescript-eslint, return-await; CWE-252
**Source:** model · confidence: high

### [minor] `module_e.mjs:141` NODE-COR-07: dueAt computed with setUTCMonth(+1) overflows at month end

```js
dueAt.setUTCMonth(dueAt.getUTCMonth() + 1);
```

**Why:** Issuing an invoice on Jan 31 gives dueAt = Mar 3 (checked in Node: 2026-01-31 becomes 2026-03-03), and Oct 31 gives Dec 1; the wrong due date is stored on the invoice. Only month-end issue dates are affected and the route is admin-gated, so minor (C2/R2).
**Fix:** Clamp the day: set the date to the 1st of next month, then min(originalDay, daysInThatMonth), or use a date library.
**Cite:** MDN, Date.prototype.setMonth (overflow rolls into the next month); CWE-682
**Source:** model · confidence: high

### [nit] `module_c.mjs:90` NODE-COR-14: Loose equality between a status string and a string literal

```js
if (user.status == 'disabled') {
```

**Why:** `status` is a string column compared with a string literal, so coercion cannot change the result (X-SEV-08): reader cost only.
**Fix:** if (user.status === 'disabled') {
**Cite:** ECMA-262 IsLooselyEqual; ESLint docs, eqeqeq
**Source:** eslint (eqeqeq) · confidence: high

### [nit] `module_c.mjs:93` X-DIFF-02: Commented-out token issuance left in

```js
// const token = jwt.sign({ id: user.id }, JWT_SECRET, { expiresIn: '7d' });
```

**Why:** Dead code that readers cannot tell from a plan or a warning (it also records a 7-day expiry that the live code does not use); version control keeps the old code.
**Fix:** Delete the line; if the decision matters, replace it with one sentence saying why the TTL is 1h.
**Cite:** Martin, Clean Code ch. 4, Commented-Out Code; SonarSource rule S125
**Source:** model · confidence: high

### [nit] `module_e.mjs:7` NODE-MAINT-01: Unused import randomUUID

```js
import { randomUUID } from 'node:crypto';
```

**Why:** `randomUUID` is imported but never used (reader cost only).
**Fix:** Remove the import.
**Cite:** ESLint docs, no-unused-vars
**Source:** eslint (no-unused-vars) · confidence: high

### [nit] `module_e.test.mjs:21` NODE-TEST-05: Fixed port 4100 for the test server

```js
server = app.listen(4100);
```

**Why:** A fixed port collides when suites run in parallel or on a busy CI host (test-code runtime problem, so D3 nit).
**Fix:** server = app.listen(0); const { port } = server.address(); and build BASE_URL from it.
**Cite:** Martin Fowler, Eradicating Non-Determinism in Tests; Node.js docs, server.listen (port 0)
**Source:** model · confidence: high

## Questions

None.

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
