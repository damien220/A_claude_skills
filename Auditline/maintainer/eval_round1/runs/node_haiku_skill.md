# Auditline report

**Scope:** file (module_a.mjs, module_b.mjs, module_c.mjs, module_e.mjs, module_e.test.mjs) · **Mode:** full · **Languages:** node
**Tools:** eslint: ran (bundled fallback config; 4 results dropped, reasons below) · tsc: skipped (no tsconfig.json)
**Coverage:** all 5 files in scope

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 5 | 8 | 2 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.mjs:10` NODE-SEC-02: Hardcoded JWT signing secret in source

```js
const JWT_SECRET = 'c0mmunity-jwt-s1gning-k3y-2024';
```

**Why:** The signing key is committed to the repository. Anyone who reads it can mint a token with any `sub` and `role`, including admin, and authenticate() and issueToken() both accept it. Reachable by anyone who can read the code, and the key is already leaked at commit, so reachability does not lower it. Rotate the key after the fix.
**Fix:** const JWT_SECRET = requireEnv('JWT_SECRET');   // set from the environment or secret manager, then rotate the leaked key
**Cite:** CWE-798; OWASP A07:2021 Identification and Authentication Failures
**Source:** model · confidence: high

### [blocker] `module_c.mjs:85` NODE-SEC-20: bcrypt.compare not awaited: login accepts any password

```js
const valid = bcrypt.compare(password, user.password_hash);
```

**Why:** bcrypt.compare returns a Promise, which is always truthy, so `!valid` is false and the password is never checked. Any existing account logs in with any password that passes the schema. Signup is open, so the reach is anonymous (R1).
**Fix:** const valid = await bcrypt.compare(password, user.password_hash);
**Cite:** CWE-287; CWE-285; OWASP A07:2021 Identification and Authentication Failures; ECMA-262 ToBoolean (a Promise is truthy)
**Source:** model · confidence: high

### [blocker] `module_c.mjs:104` NODE-SEC-01: Member search query concatenated into SQL

```js
WHERE status = 'active' AND display_name ILIKE '%${q}%'
```

**Why:** The request value q is interpolated into the SQL text on GET /members/search. Signup is open, so any anonymous caller who can sign up reaches it (R1). A crafted q such as `%' OR '1'='1` or a UNION reads other rows or tables.
**Fix:** const pattern = `%${q.replace(/[\\%_]/g, '\\$&')}%`;  // escape as module_a does, then: WHERE ... display_name ILIKE $1 ... LIMIT $2, with [pattern, limit]
**Cite:** CWE-89; OWASP A03:2021 Injection
**Source:** model · confidence: high

### [blocker] `module_e.mjs:84` NODE-SEC-04: Team usage route registered before the auth and admin middleware

```js
app.get('/api/admin/teams/:teamId/usage', asyncHandler(async (req, res) => {
```

**Why:** Express runs middleware in registration order. app.use('/api', authenticate) (line 92) and app.use('/api/admin', requireRole('admin')) (line 93) come after this route, so GET /api/admin/teams/:teamId/usage answers with no token and returns the usage of any team (R1). The admin-role test at module_e.test.mjs:47-51 would fail on this route.
**Fix:** Register this route after app.use('/api/admin', requireRole('admin')) (line 93), or move it into an admin router that has both middlewares attached.
**Cite:** CWE-862; OWASP A01:2021 Broken Access Control; Express docs, 'Using middleware' (order of loading matters)
**Source:** model · confidence: high

### [blocker] `module_e.mjs:122` NODE-SEC-04: Document delete does not check the caller owns or shares the document

```js
app.delete('/api/documents/:id', asyncHandler(async (req, res) => {
  const { rowCount } = await pool.query('DELETE FROM documents WHERE id = $1', [req.params.id]);
```

**Why:** The delete is keyed on the id alone. authenticate (line 92) only proves a valid token, so any authenticated caller can delete any document in any team by its UUID. UUIDs are not authorization. Assumes any token holder can obtain a token (issuance is outside this file), which is why reachability is R1.
**Fix:** await pool.query('DELETE FROM documents WHERE id = $1 AND owner_id = $2', [req.params.id, req.user.sub]); then return 404 when rowCount is 0 (add the share rule if editors may delete).
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; OWASP Insecure Direct Object Reference Prevention Cheat Sheet
**Source:** model · confidence: high

### [major] `module_c.mjs:60` NODE-PERF-02: Blocking bcrypt call inside the signup handler

```js
const passwordHash = bcrypt.hashSync(password, BCRYPT_ROUNDS);
```

**Why:** At 12 rounds the hash takes on the order of 250 ms of CPU. The sync call holds the event loop, so every concurrent request waits for each signup (C2, R1).
**Fix:** const passwordHash = await bcrypt.hash(password, BCRYPT_ROUNDS);
**Cite:** Node.js docs, "Don't Block the Event Loop (or the Worker Pool)"
**Source:** eslint (`n/no-sync`) · confidence: high

### [major] `module_c.mjs:71` NODE-SEC-18: Stack trace and internal error message returned to anonymous callers

```js
return reply.code(500).send({ error: err.message, stack: err.stack });
```

**Why:** Any signup failure, including database errors that name tables and columns, sends the stack trace to any anonymous caller (C2 information exposure, R1). The error is not logged here at all.
**Fix:** req.log.error({ err }, 'signup failed'); return reply.code(500).type('application/problem+json').send({ type: 'about:blank', title: 'internal server error', status: 500 });
**Cite:** CWE-209; OWASP A05:2021 Security Misconfiguration; RFC 9457
**Source:** model · confidence: high

### [major] `module_e.mjs:49` NODE-COR-09: Read-modify-write race in invoice subtotal

```js
subtotalCents += await meterChargeCents(teamId, meter, start, end);
```

**Why:** The left side of += is read before the await. All three meter callbacks read subtotalCents as 0, so only the last meter to resolve is kept. With 1000 cents per meter the subtotal is 1000, not 3000, and amount_due and the stored invoice are wrong (money, C1). Reachability is R2 because the invoice route sits behind requireRole('admin') visible in code (D1). The one test that runs (module_e.test.mjs:55) expects 3000 and would catch it.
**Fix:** const parts = await Promise.all(METERS.map((meter) => meterChargeCents(teamId, meter, start, end)));
  const subtotalCents = parts.reduce((a, b) => a + b, 0);
**Cite:** CWE-362; CWE-367
**Source:** eslint (`require-atomic-updates`) · confidence: high

### [major] `module_e.mjs:52` NODE-COR-08: Tax rounded through binary floats before the stored invoice total

```js
const amountDue = Math.round((subtotalCents / 100) * (1 + TAX_RATE) * 100) / 100;
```

**Why:** The tax is computed as a float product and then Math.round(x * 100) / 100. An exact half-cent result can land on either side of the .5 boundary after float error, so amount_due (persisted at line 146) can differ by one cent from the exact value. Money written to the invoice table (C1), on an admin-gated route (R2). Medium confidence: the specific inputs that round wrong are not proven here; the assumption is that half-cent subtotals occur.
**Fix:** Compute in integer cents: const taxCents = Math.round((subtotalCents * 825) / 10000); amountDue cents = subtotalCents + taxCents, with the rate held as basis points (825 = 8.25%).
**Cite:** CWE-682; CWE-1339; Python docs, 'Floating Point Arithmetic' (same binary-float issue); Stripe API docs, 'Currencies' (amounts in the smallest unit)
**Source:** model · confidence: medium

### [major] `module_e.mjs:114` NODE-ERR-06: Search connection not released when the query fails

```js
} catch (err) {
  if (err.code === '57014') {
    return res.status(503).json({ error: 'search timed out, try a narrower query' });
  }
  return next(err);
```

**Why:** client.release() runs only on the success path (line 112). On the 503 timeout path and on every error passed to next(err), the checked-out client is never released. Timeouts are the expected failure for a large team (the query is capped at 2 s), so each one keeps a pool connection. After about pool-size timeouts the pool drains and every database request in the API waits. The statement_timeout set on line 103 also stays on the released connection because RESET is skipped (C2 availability, R1 for any authenticated user).
**Fix:** Move client.release() into a finally block and run RESET statement_timeout there as well.
**Cite:** node-postgres docs, 'Pooling' (a checked-out client must be released); CWE-772; CWE-404
**Source:** model · confidence: high

### [major] `module_e.test.mjs:40` NODE-TEST-02: Signature test passes whatever the server returns

```js
try {
  await fetch(`${BASE_URL}/api/documents/${DOC_ID}`, { method: 'DELETE', headers });
} catch (err) {
  expect(err.status).toBe(401);
}
```

**Why:** fetch resolves on a 401 and does not throw, so the expect in catch never runs and the test passes whatever the server does. It is the only test of token signature verification, so the auth gate has no working test (major: false confidence on auth logic).
**Fix:** const response = await fetch(`${BASE_URL}/api/documents/${DOC_ID}`, { method: 'DELETE', headers }); expect(response.status).toBe(401);
**Cite:** Jest docs, async matchers and expect (assertions must run and be awaited)
**Source:** model · confidence: high

### [major] `module_e.test.mjs:55` NODE-TEST-06: it.only narrows the suite to one test

```js
it.only('adds up every meter before tax', async () => {
```

**Why:** Jest runs only this test in the file. The authentication, admin-role, rounding, database-failure and quota-warning tests are skipped silently, including the admin-role test that fails on module_e.mjs:84 and the signature test. The suite stays green while checking much less.
**Fix:** Remove .only.
**Cite:** Jest docs, test.only and test.skip
**Source:** model · confidence: high

### [major] `module_e.test.mjs:63` NODE-TEST-02: Rounding test never awaits its assertion

```js
expect(computeInvoice(TEAM_ID, ...PERIOD)).resolves.toMatchObject({ amountDue: 64.95 });
```

**Why:** The .resolves assertion is neither returned nor awaited, so the test ends before the check runs and cannot fail. It is the only test of the tax rounding (money), so major.
**Fix:** await expect(computeInvoice(TEAM_ID, ...PERIOD)).resolves.toMatchObject({ amountDue: 64.95 });
**Cite:** Jest docs, .resolves / .rejects (return or await the assertion)
**Source:** model · confidence: high

### [minor] `module_c.mjs:89` NODE-DIFF-01: console.log left in the login handler

```js
console.log('login user', user.id, user.status);
```

**Why:** Bypasses the Fastify logger and runs on every login, which is a request path (X-SEV-07: minor). Logs no secret, so not major.
**Fix:** Delete it, or use request.log.debug({ userId: user.id }, 'login user').
**Cite:** CWE-532; OWASP Logging Cheat Sheet
**Source:** eslint (`no-console`) · confidence: high

### [minor] `module_e.mjs:66` NODE-COR-10: Mailer promise returned inside try without await, so catch never runs

```js
try {
  return mailer.sendMail({
```

**Why:** return without await inside try does not catch a rejected send. The warning is not logged and null is not returned, so the admin quota route at line 166 turns a mail failure into a 500. The test at module_e.test.mjs:73-76 expects null and would fail. Consequence C2 on an admin-gated route (R2), so minor.
**Fix:** return await mailer.sendMail({
**Cite:** ECMA-262, async function semantics (a returned rejected promise bypasses try/catch); CWE-252
**Source:** model · confidence: high

### [nit] 2 nits from eslint

Collapsed: `module_c.mjs:90` eqeqeq, `module_e.mjs:7` no-unused-vars. Remove the unused import; replace `==` with `===`.

## Questions

Low-confidence blockers or majors, and absence-of-control items, go here, not above. Questions do not change the verdict.

- `module_a.mjs:105` — Is POST /login rate-limited at a gateway or by a plugin that is not in this file? If not, it is open to credential stuffing (OWASP ASVS V2.2.1).
- `module_b.mjs:98` — If a payment webhook can arrive before the order row is committed, the event id is stored and committed at line 98 with no order applied, and every retry then returns 'duplicate', so paid_at is never set. Can an event reach the handler before its order exists?
- `module_c.mjs:52` — jwt.verify has no algorithms option. With jsonwebtoken v9 and a string secret HS256 is enforced by default, so confirm the installed version (RFC 8725 §3.1).
- `module_c.mjs:75` — Is POST /login rate-limited at a gateway or elsewhere? Nothing in this file applies a limit (OWASP ASVS V2.2.1).
- `module_c.mjs:82` — The early return for an unknown email skips bcrypt, so response time reveals whether the account exists (CWE-208). Confirm whether this is acceptable for this login flow.

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
