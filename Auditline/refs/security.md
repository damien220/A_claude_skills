# Security

Sources: OWASP Top 10:2021; OWASP Cheat Sheet Series; OWASP ASVS 4.0.3; OWASP API Security Top
10 2023; MITRE CWE; RFC 6265, RFC 8725, RFC 9110, RFC 9457; WHATWG Fetch and URL Standards;
Python, Node.js, React, Next.js and library docs as cited per rule.

## Contents

1. How to use this ref
2. OWASP Top 10:2021 mapping
3. A01 Broken Access Control
4. A02 Cryptographic Failures
5. A03 Injection
6. A04 Insecure Design
7. A05 Security Misconfiguration
8. A06 Vulnerable and Outdated Components
9. A07 Identification and Authentication Failures
10. A08 Software and Data Integrity Failures
11. A09 Security Logging and Monitoring Failures
12. A10 Server-Side Request Forgery
13. Do not flag
14. Security-only mode

## 1. How to use this ref

- **Edition.** Categories are OWASP Top 10:**2021**, the edition used across this skill. Cite as
  `CWE-89; OWASP A03:2021 Injection`. Do not mix editions in one report. Every security
  finding names one CWE and one OWASP category.
- **Rule IDs.** `<LANG>-SEC-NN`. The number is the concept: `PY-SEC-16`, `NODE-SEC-16` and
  `TS-SEC-16` are the same defect in three languages, and a language without the concept skips
  the number. Use the ID for the language of the file under review. `X-SEC-NN` is for
  manifests and lockfiles, which are not language code.
- **Trace source to sink before rating.** Sources: request path, query, body, headers and
  cookies; uploaded files and their names; rows other users wrote; webhook payloads; URL
  parameters, `postMessage` and storage in the browser; LLM or third-party API output. A value
  that is a constant, or is checked against an allowlist on the path, is not a finding.
  Validation of length or format (`maxLength: 64`, `'@' in email`) does not neutralise
  injection.
- **Severity** follows `refs/severity-and-output-format.md`. Injection, auth bypass, XSS
  and hardcoded production secrets are never downgraded (X-SEV-04). Path traversal follows
  X-SEV-03. A **defense-in-depth gap** (it only matters once a second flaw exists: an XSS, a
  database leak, a network attacker) is C2, so major on an open path and minor behind a visible
  trusted-user gate (D1). Absence of a control with no line to quote is a question at most
  (X-SEV-09).
- **Confidence.** If the ownership check, sanitizer or validation might live in a helper you
  have not read, read it first. If it is still unseen, the blocker becomes a question.

## 2. OWASP Top 10:2021 mapping

| Category | Rules | Main CWEs |
|---|---|---|
| A01 Broken Access Control | PY/NODE/TS-SEC-04 IDOR · PY/NODE-SEC-03 path traversal · PY/NODE/TS-SEC-05 open redirect · PY/NODE-SEC-06 CSRF | 639, 862, 22, 601, 352 |
| A02 Cryptographic Failures | PY/NODE/TS-SEC-07 weak random · PY/NODE-SEC-08 password hashing · PY/NODE-SEC-10 timing compare · PY/NODE-SEC-11 JWT verification | 338, 916, 208, 347 |
| A03 Injection | PY/NODE-SEC-01 SQL · PY/NODE-SEC-13 NoSQL · PY/NODE-SEC-14 shell · PY/NODE-SEC-15 eval · PY/NODE/TS-SEC-16 HTML · TS-SEC-26 script URLs | 89, 943, 78, 95, 79, 1336 |
| A04 Insecure Design | PY/NODE/TS-SEC-17 client-supplied price | 602, 472 |
| A05 Security Misconfiguration | PY/NODE-SEC-09 CORS · PY/NODE-SEC-18 debug and error detail · PY/NODE-SEC-19 cookie flags | 942, 209, 489, 1004, 614 |
| A06 Vulnerable and Outdated Components | X-SEC-01 dependency changes | 1104, 1395, 829 |
| A07 Identification and Authentication Failures | PY/NODE/TS-SEC-02 hardcoded secret · PY/NODE/TS-SEC-20 un-awaited check · PY/NODE-SEC-12 TLS verification · TS-SEC-27 token in Web Storage | 798, 287, 295, 922 |
| A08 Software and Data Integrity Failures | PY/NODE-SEC-21 deserialization · PY/NODE/TS-SEC-22 mass assignment | 502, 915, 1321 |
| A09 Security Logging and Monitoring Failures | PY/NODE/TS-SEC-23 secrets in logs · PY/NODE-SEC-24 fail-open or unrecorded failure | 532, 636, 778 |
| A10 Server-Side Request Forgery | PY/NODE/TS-SEC-25 SSRF | 918 |

## 3. A01 Broken Access Control

### PY-SEC-04 · NODE-SEC-04 · TS-SEC-04 — Object read or changed by a client-supplied ID without an ownership check
- **Detect:** a route, server action or route handler takes an ID (`<int:id>`, `req.params.id`,
  `searchParams.get('id')`, an action argument, a form field) and loads, updates or deletes by
  that ID alone (`db.session.get(Model, id)`, `WHERE id = $1`, `findUnique({ where: { id } })`)
  while the current user (`current_user`, `request.user`, `req.user`, `session.user`) is in scope
  but not in the query and not compared afterwards. Also: the read route checks ownership but the
  sibling update or delete route does not; the check compares a `userId` taken from the body
  instead of the session; list endpoints filter by `?user_id=` from the query. Next.js `'use
  server'` functions are public POST endpoints: no session lookup inside is the signal. Also file
  here, so that `--security-only` keeps them: another user's data served from process-wide state
  (a module-level `currentUser`, a `QueryClient` or store shared by server-rendered requests, a
  cache key without the user or tenant: `PY/NODE/TS-COR-01`, `-COR-16`), and an authentication or
  authorization middleware registered after the route it guards (`NODE-COR-65`).
- **Default severity:** blocker when any signed-up user can reach it (C1 other users' data / R1;
  authorization bypass is an X-SEV-04 class). Not a finding for data public by design or for
  admin routes with a role gate visible in code.
- **Why:** authentication says who the caller is, not what they may touch. Sequential IDs are
  enumerable; UUIDs are not authorization (they leak in URLs, logs and shared links).
- WRONG:
  ```python
  @bp.get("/invoices/<int:invoice_id>")
  @login_required
  def get_invoice(invoice_id: int) -> ResponseReturnValue:
      invoice = db.session.get(Invoice, invoice_id)   # any logged-in user, any invoice
      return jsonify(invoice.to_dict())
  ```
  ```js
  app.delete('/notes/:id', { preHandler: authenticate }, async (req) => {
    await pool.query('DELETE FROM notes WHERE id = $1', [req.params.id]);
  });
  ```
  ```tsx
  'use server';
  export async function deleteProject(projectId: string) {
    await db.project.delete({ where: { id: projectId } });
  }
  ```
- CORRECT:
  ```python
  invoice = db.session.scalar(
      select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == current_user.id)
  )
  if invoice is None:
      abort(404)
  ```
  ```js
  const { rowCount } = await pool.query(
    'DELETE FROM notes WHERE id = $1 AND owner_id = $2', [req.params.id, req.user.sub]);
  if (rowCount === 0) return reply.code(404).send();
  ```
  ```tsx
  'use server';
  export async function deleteProject(projectId: string) {
    const session = await auth();                       // the app's session helper
    if (!session) throw new Error('Unauthorized');
    await db.project.deleteMany({ where: { id: projectId, ownerId: session.user.id } });
  }
  ```
- **Fix:** scope every query by the owner or tenant taken from the session; return 404 on a
  miss; keep the rule in one policy helper.
- **Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; OWASP Authorization Cheat
  Sheet; OWASP Insecure Direct Object Reference Prevention Cheat Sheet; Next.js docs, "Data
  Security" (Server Actions are public endpoints).
- **Tool code:** none.

### PY-SEC-03 · NODE-SEC-03 — Request-controlled path reaches the filesystem
- **Detect:** see X-SEV-03 for `open`, `send_file`, `os.path.join`, `fs.readFile`,
  `createReadStream`. Also: uploaded names (`f.save(os.path.join(DIR, f.filename))`, multer
  `originalname`); archive extraction (`ZipFile.extractall`, `tarfile.extractall` without
  `filter="data"`) of uploads; a containment check by string prefix without a trailing
  separator (`/srv/files` also matches `/srv/files-old`); a `.endswith(".csv")` suffix check.
- **Default severity:** per X-SEV-03: blocker when any caller reaches it; major only behind a
  trusted-user gate visible as code (D1).
- **Why:** `../` segments or an absolute path read or overwrite any file the process can.
- WRONG:
  ```python
  upload = request.files["doc"]
  upload.save(os.path.join(UPLOAD_DIR, upload.filename))   # "../../app/config.py"
  ```
  ```js
  const file = path.join(EXPORT_DIR, req.params.name);
  return reply.send(fs.createReadStream(file));
  ```
- CORRECT:
  ```python
  upload.save(os.path.join(UPLOAD_DIR, secure_filename(upload.filename or "upload")))
  ```
  ```js
  const base = path.resolve(EXPORT_DIR);
  const file = path.resolve(base, req.params.name);
  if (!file.startsWith(base + path.sep)) return reply.code(404).send();
  return reply.send(fs.createReadStream(file));
  ```
- **Fix:** Flask `send_from_directory`, Werkzeug `secure_filename`; `resolve()` plus
  `is_relative_to` / `startsWith(base + path.sep)`; `tarfile` extraction filters; server-generated
  storage names.
- **Cite:** CWE-22; OWASP A01:2021 Broken Access Control; Werkzeug docs, `secure_filename`;
  PEP 706 (tarfile extraction filters); Node.js docs, `path.resolve`.
- **Tool code:** `[ruff: S202]` (tar extraction only); `[eslint: security/detect-non-literal-fs-filename]`
  (noisy; confirm the source).

### PY-SEC-05 · NODE-SEC-05 · TS-SEC-05 — Redirect target taken from the request
- **Detect:** `redirect(request.args["next"])`, `reply.redirect(req.query.returnTo)`,
  `res.redirect(req.query.url)`, `window.location.assign(params.get('next'))`,
  `router.push(searchParams.get('redirect'))`. Bypassable checks: `startswith("/")` (`//evil.com`
  and `/\evil.com` are cross-origin), `"example.com" in url`, `startsWith('https://example.com')`
  (`https://example.com.evil.net`), string checks before the browser strips tabs and newlines.
- **Default severity:** major (C2 phishing that borrows the site's origin / R1); blocker when the
  redirect carries a credential to the target (OAuth code or token, magic-link token, session ID
  in the URL), which is C1.
- **Why:** users trust the first hostname they see; the hop to an attacker page looks like a
  link from the real site.
- WRONG:
  ```python
  return redirect(request.args.get("next", "/"))
  ```
  ```js
  if (!req.query.returnTo.startsWith('/')) return reply.redirect('/');   // "//evil.com" passes
  return reply.redirect(req.query.returnTo);
  ```
  ```tsx
  window.location.assign(new URLSearchParams(location.search).get('next') ?? '/');
  ```
- CORRECT:
  ```python
  SAFE_NEXT = {"/dashboard", "/billing", "/settings"}
  target = request.args.get("next", "/")
  return redirect(target if target in SAFE_NEXT else "/")
  ```
  ```js
  const next = new URL(req.query.returnTo ?? '/', APP_ORIGIN);   // APP_ORIGIN = 'https://app.example.com'
  return reply.redirect(next.origin === APP_ORIGIN ? next.pathname + next.search : '/');
  ```
  ```tsx
  const next = new URL(new URLSearchParams(location.search).get('next') ?? '/', location.origin);
  window.location.assign(next.origin === location.origin ? next.pathname + next.search : '/');
  ```
- **Fix:** allowlist, or parse with a real URL parser against the own origin and compare
  origins; Django `url_has_allowed_host_and_scheme`; the same in Node with `new URL(next, base)`.
- **Cite:** CWE-601; OWASP A01:2021 Broken Access Control; OWASP Unvalidated Redirects and
  Forwards Cheat Sheet; WHATWG URL Standard (tab and newline removal, `\` as `/` in special
  schemes).
- **Tool code:** none.

### PY-SEC-06 · NODE-SEC-06 — State change reachable cross-site with cookie authentication (CSRF)
- **Detect:** only where authentication rides on cookies. (1) A state-changing handler on GET;
  (2) CSRF protection removed for a cookie-authenticated route (`@csrf_exempt`,
  `csrf.exempt(bp)`, `WTF_CSRF_ENABLED = False` outside tests); (3) the session cookie set to
  `SameSite=None` and the route checks no token; (4) a route added without the CSRF hook its
  sibling routes use.
- **Default severity:** blocker when the action changes credentials, email or roles, or moves
  money (C1 account takeover or loss / R1: any page the victim visits); major for other state
  changes (C2). When the app's CSRF middleware is not visible, a question (X-SEV-09).
- **Why:** the browser attaches cookies to cross-site requests, so another site can submit the
  action as the victim.
- WRONG:
  ```python
  @bp.get("/account/email")                     # GET with a side effect, cookie session
  @login_required
  def change_email() -> ResponseReturnValue:
      current_user.email = request.args["email"]
      db.session.commit()
      return redirect("/account")
  ```
  ```js
  app.use(session({ secret: SESSION_SECRET, cookie: { sameSite: 'none', secure: true } }));
  app.post('/settings/email', requireLogin, updateEmail);   // no CSRF token check
  ```
- CORRECT:
  ```python
  csrf = CSRFProtect(app)                       # Flask-WTF: token required on POST

  @bp.post("/account/email")
  @login_required
  def change_email() -> ResponseReturnValue: ...
  ```
  ```js
  app.use(session({ secret: SESSION_SECRET,
    cookie: { sameSite: 'lax', secure: true, httpOnly: true } }));
  app.post('/settings/email', requireLogin, verifyCsrfToken, updateEmail);
  ```
- **Fix:** state changes only on unsafe methods; a synchronizer or signed double-submit token
  (Flask-WTF `CSRFProtect`, Django `CsrfViewMiddleware`, `@fastify/csrf-protection`); `SameSite`
  as defense in depth, not the only control.
- **Cite:** CWE-352; OWASP A01:2021 Broken Access Control; OWASP Cross-Site Request Forgery
  Prevention Cheat Sheet; RFC 9110 §9.2.1 (safe methods); Django docs, "Cross Site Request
  Forgery protection".
- **Tool code:** none.

## 4. A02 Cryptographic Failures

### PY-SEC-07 · NODE-SEC-07 · TS-SEC-07 — Non-cryptographic random used for a security value
- **Detect:** `random.choice/choices/randint/getrandbits`, `uuid.uuid1()`, `time.time()` or a hash
  of a timestamp or email; JS `Math.random()`, `Date.now().toString(36)`. Look at what the value
  becomes: password-reset, email-verification or invite tokens, session IDs, API keys, OTP
  codes, OAuth `state`, PKCE `code_verifier`, `nonce`, CSRF tokens, unguessable file names.
  `uuid.uuid4()` and `crypto.randomUUID()` draw from a CSPRNG and are fine.
- **Default severity:** blocker when the value grants access (C1 account takeover / R1):
  Mersenne Twister and V8's `Math.random` state can be recovered from observed outputs. Major
  when it protects a low-value object (an unlisted share link to non-sensitive data). Not
  flagged for jitter, sampling, shuffling or test data.
- **Why:** a predictable token is a guessable password.
- WRONG:
  ```python
  token = "".join(random.choices(string.ascii_letters + string.digits, k=32))
  ```
  ```js
  const resetToken = Math.random().toString(36).slice(2);
  ```
  ```tsx
  const state = Math.random().toString(36).slice(2);      // OAuth state
  sessionStorage.setItem('oauth_state', state);
  ```
- CORRECT:
  ```python
  token = secrets.token_urlsafe(32)
  ```
  ```js
  import { randomBytes } from 'node:crypto';
  const resetToken = randomBytes(32).toString('base64url');
  ```
  ```tsx
  const state = crypto.randomUUID();                      // Web Crypto CSPRNG
  ```
- **Fix:** Python `secrets`; Node `crypto.randomBytes` / `randomUUID`; browser
  `crypto.getRandomValues` / `crypto.randomUUID`.
- **Cite:** CWE-338; CWE-330; OWASP A02:2021 Cryptographic Failures; Python docs, `random`
  (warning: not for security) and `secrets`; Node.js docs, `crypto.randomBytes`; MDN,
  `Math.random()` (not cryptographically secure).
- **Tool code:** `[ruff: S311]`; JS/TS: none.

### PY-SEC-08 · NODE-SEC-08 — Password stored with a fast, unsalted or reversible hash
- **Detect:** `hashlib.sha256/sha512/md5/sha1` or `crypto.createHash(...)` applied to a password,
  even salted; `pbkdf2_hmac` with a low iteration count; bcrypt cost below 10; reversible
  encryption (`Fernet(key).encrypt(password)`); a password column compared in plain text.
- **Default severity:** major (C2: the hashes fall to offline cracking once the table leaks /
  R1). Plain text or reversible storage is also major; say so in the title.
- **Why:** general-purpose hashes run billions of times per second on a GPU; password hashes are
  built to be slow and salted.
- WRONG:
  ```python
  user.password_hash = hashlib.sha256(salt + password.encode()).hexdigest()
  ```
  ```js
  const hash = createHash('sha256').update(password).digest('hex');
  ```
- CORRECT:
  ```python
  user.password_hash = PasswordHasher().hash(password)     # argon2-cffi, Argon2id
  ```
  ```js
  const hash = await bcrypt.hash(password, 12);            // async: no event-loop block
  ```
- **Fix:** Argon2id, scrypt, bcrypt or PBKDF2 with the parameters in the OWASP Password Storage
  Cheat Sheet; rehash on next login.
- **Cite:** CWE-916; CWE-759; OWASP A02:2021 Cryptographic Failures; OWASP Password Storage
  Cheat Sheet; argon2-cffi docs, `PasswordHasher`.
- **Tool code:** `[ruff: S324]` (md5/sha1 only; SHA-256 on a password passes); Node: none.

### PY-SEC-10 · NODE-SEC-10 — Secret or MAC compared with a non-constant-time operator
- **Detect:** `==`, `!=`, `===` or `Buffer.equals` between a request-supplied value and a
  secret: a webhook signature against the computed HMAC, an API key header against the stored
  key, a reset token against the stored token. Not this rule: bcrypt/argon2 `verify` (constant
  time inside), and login-timing user enumeration (a question; severity ref §6).
- **Default severity:** major (C2 information exposure: the expected value leaks byte by byte to
  a caller who can send many requests; network noise makes it hard, which keeps it below
  blocker / R1); minor behind a visible trusted-user gate (D1).
- **Why:** string comparison returns at the first differing byte, so response time reveals the
  matching prefix.
- WRONG:
  ```python
  if hmac.new(key, body, "sha256").hexdigest() == request.headers["X-Signature"]:
  ```
  ```js
  if (req.headers['x-api-key'] === process.env.ADMIN_API_KEY) {
  ```
- CORRECT:
  ```python
  expected = hmac.new(key, body, "sha256").hexdigest()
  if hmac.compare_digest(expected, request.headers.get("X-Signature", "")):
  ```
  ```js
  const digest = (s) => createHash('sha256').update(String(s ?? '')).digest();
  if (timingSafeEqual(digest(req.headers['x-api-key']), digest(process.env.ADMIN_API_KEY))) {
  ```
- **Fix:** `hmac.compare_digest`; `crypto.timingSafeEqual` on equal-length buffers (hash both
  sides first, since it throws on a length mismatch).
- **Cite:** CWE-208; OWASP A02:2021 Cryptographic Failures; Python docs, `hmac.compare_digest`;
  Node.js docs, `crypto.timingSafeEqual`.
- **Tool code:** `[eslint: security/detect-possible-timing-attacks]` (when eslint-plugin-security
  is installed); Python: none.

### PY-SEC-11 · NODE-SEC-11 — JWT accepted without signature, algorithm or expiry verification
- **Detect:**
  - jsonwebtoken `jwt.decode(token)` feeding an auth decision (`decode` never verifies); PyJWT
    `jwt.decode(token, options={"verify_signature": False})`; python-jose
    `get_unverified_claims`; claims read from an unverified header.
  - `algorithms` containing `"none"`, taken from the token header, or mixing `HS*` with
    `RS*`/`ES*` while verifying with a public key (algorithm confusion).
  - `ignoreExpiration: true`, `options={"verify_exp": False}`, or a bearer session token signed
    with no `exp` / `expiresIn`.
  - `kid` from the header used as a file path or SQL value (also PY/NODE-SEC-03 or -01).
- **Default severity:** blocker when an unverified or `none`-signed token is accepted, or when the
  shown verify call allows algorithm confusion (auth bypass, X-SEV-04). Major for disabled or
  missing expiry (C2: a stolen token never dies). A verify call without an `algorithms` list on
  a library that derives it from the key type is a question at most (X-SEV-09, severity ref §6).
- **Why:** whoever can write the claims can choose `sub` and `role`.
- WRONG:
  ```js
  const claims = jwt.decode(req.headers.authorization.slice(7));   // signature never checked
  if (claims.role === 'admin') { /* … */ }
  ```
  ```python
  claims = jwt.decode(token, options={"verify_signature": False})
  ```
- CORRECT:
  ```js
  const claims = jwt.verify(token, PUBLIC_KEY,
    { algorithms: ['RS256'], issuer: ISSUER, audience: AUDIENCE });
  ```
  ```python
  claims = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], audience=AUDIENCE,
                      issuer=ISSUER, options={"require": ["exp", "sub"]})
  ```
- **Fix:** verify with a fixed algorithm allowlist, issuer and audience; require `exp`; never
  branch on decoded-but-unverified claims on the server.
- **Cite:** CWE-347; CWE-613 (no expiry); OWASP A02:2021 Cryptographic Failures; RFC 8725 §2.1
  and §3.1; jsonwebtoken README (`jwt.decode` does not verify the signature); PyJWT docs,
  `jwt.decode`.
- **Tool code:** none.

## 5. A03 Injection

### PY-SEC-01 · NODE-SEC-01 — SQL text built from request input
- **Detect:** f-string, `%`, `.format()`, `+` or a template literal building the SQL passed to
  `execute`, `executemany`, `text()`, `.raw()`, `.extra()`, `pool.query`, `knex.raw`,
  `sequelize.query`, Prisma `$queryRawUnsafe` / `$executeRawUnsafe`. Trace the interpolated
  value to request input or a user-written row. Identifiers (`ORDER BY ${sort}`, table names)
  cannot be bound and need an allowlist. Prisma's `$queryRaw` tagged template and driver `sql`
  tags bind values and are fine.
- **Default severity:** blocker (X-SEV-04); never downgraded by a login anyone can pass. No
  finding when every interpolated value is a constant or an allowlisted identifier; drop the
  `S608` result with that reason.
- **Why:** input becomes SQL syntax: any row read or changed, login bypassed.
- WRONG:
  ```python
  query = f"SELECT id, name FROM accounts WHERE owner = '{owner}'"
  rows = conn.execute(query).fetchall()
  ```
  ```js
  const { rows } = await pool.query(
    `SELECT id, title FROM posts WHERE title ILIKE '%${req.query.term}%' ORDER BY ${req.query.sort}`);
  ```
- CORRECT:
  ```python
  rows = conn.execute("SELECT id, name FROM accounts WHERE owner = ?", (owner,)).fetchall()
  ```
  ```js
  const SORT = { new: 'created_at DESC', title: 'title ASC' };
  const order = SORT[req.query.sort] ?? SORT.new;               // allowlisted identifier
  const { rows } = await pool.query(
    `SELECT id, title FROM posts WHERE title ILIKE '%' || $1 || '%' ORDER BY ${order}`,
    [req.query.term]);
  ```
- **Fix:** bound parameters (`?`, `%s`, `$1`, `:name`) or the ORM query builder; allowlist
  identifiers.
- **Cite:** CWE-89; OWASP A03:2021 Injection; OWASP SQL Injection Prevention Cheat Sheet; Python
  docs, `sqlite3` ("How to use placeholders to bind values in SQL queries"); node-postgres docs,
  "Queries" (parameterized query).
- **Tool code:** `[ruff: S608]`; Node: none.

### PY-SEC-13 · NODE-SEC-13 — NoSQL operator injection
- **Detect:** request JSON placed into a MongoDB filter without forcing scalar types:
  `find_one({"email": body["email"], "reset_token": body["token"]})`,
  `Users.findOne({ resetToken: req.body.token })`; a body schema that does not pin
  `type: 'string'`; Express 4's default `qs` parser turning `?token[$ne]=x` into an object;
  `$where` built from strings; `$regex` from input.
- **Default severity:** blocker (injection class, X-SEV-04): `{"$ne": null}` matches any row, so
  a reset or login filter accepts any account.
- **Why:** an object where a string was expected becomes a query operator.
- WRONG:
  ```python
  user = db.users.find_one({"email": body["email"], "reset_token": body["token"]})
  ```
  ```js
  const user = await Users.findOne({ email: req.body.email, resetToken: req.body.token });
  ```
- CORRECT:
  ```python
  if not isinstance(body.get("token"), str):
      abort(400)
  user = db.users.find_one({"email": body["email"], "reset_token": {"$eq": body["token"]}})
  ```
  ```js
  const { email, token } = req.body;
  if (typeof email !== 'string' || typeof token !== 'string') return reply.code(400).send();
  const user = await Users.findOne({ email, resetToken: { $eq: token } });
  ```
- **Fix:** schema-validate scalar types; `$eq` for user values; Mongoose `sanitizeFilter`.
- **Cite:** CWE-943; OWASP A03:2021 Injection; OWASP WSTG, "Testing for NoSQL Injection";
  Mongoose docs, `sanitizeFilter`.
- **Tool code:** none.

### PY-SEC-14 · NODE-SEC-14 — Shell command built from input
- **Detect:** `subprocess.*(…, shell=True)`, `os.system`, `os.popen` with interpolated values;
  Node `exec`/`execSync` with a template literal, `spawn(cmd, { shell: true })`,
  `execFile('sh', ['-c', …])`. Argument injection: a user value in list form that can start with
  `-` (`git clone --upload-pack=…`).
- **Default severity:** blocker (injection, X-SEV-04: code execution). Argument injection is
  rated by what the option can do; an option that runs a program is a blocker.
- **Why:** shell metacharacters (`;`, `$( )`, backticks) run attacker commands as the service.
- WRONG:
  ```python
  subprocess.run(f"git clone {repo_url} {dest}", shell=True, check=True)
  ```
  ```js
  await execAsync(`git clone ${req.body.repoUrl} /tmp/build`);
  ```
- CORRECT:
  ```python
  subprocess.run(["git", "clone", "--", repo_url, dest], check=True, timeout=120)
  ```
  ```js
  await execFileAsync('git', ['clone', '--', req.body.repoUrl, buildDir]);
  ```
- **Fix:** argument list without a shell; `--` before user operands; validate scheme and
  format (`https://` only).
- **Cite:** CWE-78; CWE-88; OWASP A03:2021 Injection; OWASP OS Command Injection Defense Cheat
  Sheet; Python docs, `subprocess` "Security Considerations"; Node.js docs, `child_process.exec`
  (never pass unsanitized input) and `execFile`.
- **Tool code:** `[ruff: S602, S604, S605]`; `[eslint: security/detect-child-process]`.

### PY-SEC-15 · NODE-SEC-15 — Input evaluated as code
- **Detect:** `eval`, `exec`, `compile` on request data (calculators, rule or filter engines,
  "formula" fields), `eval(x, {"__builtins__": {}})` presented as a sandbox; Node `eval`,
  `new Function(body)`, `setTimeout(string)`, `vm.runInNewContext` as a sandbox,
  `import(userPath)`; dispatch tables indexed by user keys on plain objects
  (`ops[req.body.op]` reaches `constructor`).
- **Default severity:** blocker (code injection, X-SEV-04).
- **Why:** removing builtins or using `vm` is not isolation; known escapes reach the runtime.
- WRONG:
  ```python
  total = eval(request.json["formula"], {"__builtins__": {}})
  ```
  ```js
  const result = vm.runInNewContext(req.body.expression, { price, qty });
  ```
- CORRECT:
  ```python
  value = ast.literal_eval(request.json["value"])     # literals only
  ```
  ```js
  const OPS = new Map([['add', (a, b) => a + b], ['mul', (a, b) => a * b]]);
  const op = OPS.get(req.body.op);
  if (!op) return reply.code(400).send();
  ```
- **Fix:** `ast.literal_eval`, a parser with an operator allowlist, or a `Map` of permitted
  operations; never `vm` for untrusted code.
- **Cite:** CWE-95; CWE-94; OWASP A03:2021 Injection; Python docs, `eval` and
  `ast.literal_eval`; Node.js docs, `vm` ("not a security mechanism").
- **Tool code:** `[ruff: S307, S102]`; `[eslint: no-eval, no-implied-eval, no-new-func]`,
  `[eslint: security/detect-eval-with-expression]`.

### PY-SEC-16 · NODE-SEC-16 · TS-SEC-16 — User-controlled text rendered as HTML
- **Detect:**
  - React: `dangerouslySetInnerHTML={{ __html: x }}`, `ref.current.innerHTML =`,
    `insertAdjacentHTML`, `document.write`, markdown rendered with raw HTML enabled; `x` is
    user-written or third-party (reviews, comments, bios, CMS, translation or LLM output).
  - Python: `Markup(f"…{x}")`, `|safe` or `{% autoescape false %}` on user data,
    `Environment(autoescape=False)`, HTML built in an f-string and returned,
    `render_template_string(user_text)` (template injection: code execution).
  - Node: HTML built with template literals and sent (`reply.type('text/html').send(...)`),
    EJS `<%- x %>`, Handlebars `{{{ x }}}`, Pug `!{x}`.
  - A sanitizer whose output is modified or concatenated afterwards.
- **Default severity:** blocker (X-SEV-04), stored or reflected. Not a finding: constants,
  sanitizer output passed unchanged, HTML produced at build time from repository content.
- **Why:** the attacker's script runs in the victim's session on the site's origin.
- WRONG:
  ```tsx
  <article dangerouslySetInnerHTML={{ __html: post.bioHtml }} />
  ```
  ```python
  return render_template_string(f"<h1>Hello {request.args['name']}</h1>")   # {{7*7}} runs
  ```
  ```js
  reply.type('text/html').send(`<p>No results for ${req.query.q}</p>`);
  ```
- CORRECT:
  ```tsx
  <article>{post.bio}</article>
  <article dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(post.bioHtml) }} />
  ```
  ```python
  return render_template_string("<h1>Hello {{ name }}</h1>", name=request.args["name"])
  ```
  ```js
  reply.type('text/html').send(`<p>No results for ${escapeHtml(req.query.q)}</p>`);
  ```
- **Fix:** render as text; sanitize with DOMPurify when HTML is required; autoescaping templates
  with user data as context, never as template source.
- **Cite:** CWE-79; CWE-1336 (template injection); OWASP A03:2021 Injection; OWASP Cross Site
  Scripting Prevention Cheat Sheet; React docs, `dangerouslySetInnerHTML`; Jinja docs,
  "Autoescaping"; Flask docs, "Security Considerations".
- **Tool code:** `[eslint-plugin-react: no-danger]`; `[ruff: S701, S704]`; Node: none.

### TS-SEC-26 — User-controlled URL in `href`, `src` or navigation
- **Detect:** `<a href={profile.website}>`, `<iframe src={embedUrl}>`, `window.open(url)`,
  `location.href = url`, `<Link href={…}>` with a user-written or query-string URL and no scheme
  check. `javascript:` runs script on click; `data:` can carry HTML.
- **Default severity:** blocker when another user's stored value or a crafted link reaches it
  (XSS, X-SEV-04). Not flagged for the current user's own unsaved input (self-XSS).
- **Why:** JSX escapes text, not URL schemes. React 16.9 only deprecated `javascript:` URLs with a
  warning; do not rely on the framework to block them.
- WRONG:
  ```tsx
  <a href={user.website} rel="nofollow">{user.website}</a>
  ```
- CORRECT:
  ```tsx
  function safeHref(raw: string): string | undefined {
    try {
      const url = new URL(raw);
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined;
    } catch {
      return undefined;
    }
  }
  <a href={safeHref(user.website)} rel="nofollow ugc">{user.website}</a>
  ```
- **Fix:** parse with `new URL` and allow only `http:`/`https:` (plus `mailto:` where needed).
- **Cite:** CWE-79; OWASP A03:2021 Injection; React blog, "React v16.9.0 and the Roadmap Update"
  (deprecating `javascript:` URLs); OWASP Cross Site Scripting Prevention Cheat Sheet.
- **Tool code:** `[eslint-plugin-react: jsx-no-script-url]` (literal `javascript:` strings only).

## 6. A04 Insecure Design

### PY-SEC-17 · NODE-SEC-17 · TS-SEC-17 — Price, amount or entitlement taken from the client
- **Detect:** the server charges or grants from client-sent `price`, `amount`, `total`,
  `discount`, `plan`, `trial_days`, `is_paid`: `stripe.PaymentIntent.create(amount=body[...])`,
  `paymentIntents.create({ amount: req.body.amount })`, a Next.js server action reading
  `priceCents` from `FormData`; quantities with no lower bound (negative totals); coupons
  applied without a server lookup. Client code posting `price` or `total` is a signal to check
  the server, and a question when the server is not in scope.
- **Default severity:** blocker (C1 money loss / R1). A display-only total in the client is not a
  finding.
- **Why:** every field in a request is attacker-chosen; the price must come from the server.
- WRONG:
  ```python
  stripe.PaymentIntent.create(amount=payload["amount"], currency="usd")
  ```
  ```js
  await stripe.paymentIntents.create({ amount: req.body.amount, currency: 'usd' });
  ```
  ```tsx
  'use server';
  export async function checkout(form: FormData) {
    await charge({ sku: String(form.get('sku')), amountCents: Number(form.get('priceCents')) });
  }
  ```
- CORRECT:
  ```python
  amount = sum(PRICES[item.sku] * item.qty for item in cart.items)   # qty validated 1..99
  stripe.PaymentIntent.create(amount=amount, currency="usd")
  ```
  ```js
  const amount = await priceCart(req.user.sub);                      // server-side prices
  await stripe.paymentIntents.create({ amount, currency: 'usd' });
  ```
  ```tsx
  const product = await db.product.findUniqueOrThrow({ where: { sku } });
  await charge({ sku, amountCents: product.priceCents });
  ```
- **Fix:** take only identifiers and quantities from the client; look up prices and entitlements
  on the server; bound quantities.
- **Cite:** CWE-602; CWE-472; OWASP A04:2021 Insecure Design; OWASP WSTG, Business Logic
  Testing.
- **Tool code:** none.

## 7. A05 Security Misconfiguration

### PY-SEC-09 · NODE-SEC-09 — CORS reflects any origin with credentials
- **Detect:** `cors({ origin: true, credentials: true })` and `@fastify/cors` with
  `origin: true` (both reflect the request's `Origin`), an origin callback that always allows,
  `endsWith('example.com')` or unanchored regex checks, `null` allowed; in Python, a handler or
  `after_request` that copies `request.headers["Origin"]` into `Access-Control-Allow-Origin` with
  `Allow-Credentials: true`. Matters only when authentication uses cookies. A missing helmet or
  other absent header is **not** this rule (X-SEV-09: a question at most).
- **Default severity:** blocker when cookie-authenticated responses carry user data (C1: any
  website reads them in the victim's session / R1); a question when the auth mechanism is not
  visible.
- **Why:** reflection plus credentials turns the same-origin policy off for the API.
- WRONG:
  ```js
  await app.register(cors, { origin: true, credentials: true });
  ```
  ```python
  @app.after_request
  def add_cors(resp: Response) -> Response:
      resp.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "")
      resp.headers["Access-Control-Allow-Credentials"] = "true"
      return resp
  ```
- CORRECT:
  ```js
  await app.register(cors, { origin: ['https://app.example.com'], credentials: true });
  ```
  ```python
  origin = request.headers.get("Origin")
  if origin in ALLOWED_ORIGINS:                    # exact strings, not suffixes
      resp.headers["Access-Control-Allow-Origin"] = origin
      resp.headers["Access-Control-Allow-Credentials"] = "true"
      resp.headers["Vary"] = "Origin"
  ```
- **Fix:** exact-match allowlist of origins; credentials only for those.
- **Cite:** CWE-942; OWASP A05:2021 Security Misconfiguration; WHATWG Fetch Standard, "CORS
  protocol"; `cors` package README (`origin: true` reflects the request origin).
- **Tool code:** none.

### PY-SEC-18 · NODE-SEC-18 — Debug mode or internal error detail exposed
- **Detect:** `app.run(debug=True)`, `app.debug = True`, Django `DEBUG = True` in production
  settings, `FLASK_DEBUG=1` in a Dockerfile or Procfile; responses carrying
  `traceback.format_exc()`, `str(exc)` of a database error, `err.stack`, `err.message` of
  internal errors, or the raw error object (`res.status(500).json(err)`).
- **Default severity:** blocker when an interactive debugger is reachable in a deployed app (the
  Werkzeug debugger runs code: C1/R1); major for stack traces or internal messages in responses
  (C2 information exposure / R1, severity ref M4); minor for `app.run(debug=True)` under
  `if __name__ == "__main__":` (development server only, D3). Report information exposure here,
  not under the error-handling rules, so it survives `--security-only`.
- **Why:** traces reveal paths, queries and library versions; a debugger is a remote shell.
- WRONG:
  ```python
  except Exception:
      return jsonify(error="export failed", trace=traceback.format_exc()), 500
  ```
  ```js
  res.status(500).json({ message: err.message, stack: err.stack });
  ```
- CORRECT:
  ```python
  except ExportError:
      logger.exception("export failed")
      return jsonify(error="internal error", request_id=g.request_id), 500
  ```
  ```js
  req.log.error({ err }, 'export failed');
  res.status(500).type('application/problem+json')
    .json({ type: 'about:blank', title: 'Internal Server Error', status: 500 });
  ```
- **Fix:** log the detail server-side with a request ID; return a generic problem response.
- **Cite:** CWE-209; CWE-489; OWASP A05:2021 Security Misconfiguration; OWASP Error Handling
  Cheat Sheet; Flask docs, "Debug Mode" (never use the debugger in production); RFC 9457.
- **Tool code:** `[ruff: S201]`; Node: none.

### PY-SEC-19 · NODE-SEC-19 — Auth cookie set without `HttpOnly` or `Secure`
- **Detect:** a cookie carrying a session ID, JWT, refresh or remember-me token set without
  flags: Flask `resp.set_cookie("session_id", sid)` (defaults: not HttpOnly, not Secure),
  `SESSION_COOKIE_SECURE = False` in production config, Express `res.cookie('token', jwt)`
  (no HttpOnly or Secure by default), `httpOnly: false`, `sameSite: 'none'` without `secure`.
  Preference cookies are not flagged.
- **Default severity:** major for a missing `HttpOnly` or `Secure` on an auth cookie (C2 defense
  in depth: an XSS or a network attacker then takes the session / R1); minor when only
  `SameSite` is missing and PY/NODE-SEC-06 does not apply.
- **Why:** script-readable cookies turn any XSS into session theft; cookies without `Secure`
  are sent over plain HTTP.
- WRONG:
  ```python
  resp.set_cookie("session_id", session_id)
  ```
  ```js
  res.cookie('refresh_token', refreshToken, { maxAge: THIRTY_DAYS_MS });
  ```
- CORRECT:
  ```python
  resp.set_cookie("session_id", session_id, httponly=True, secure=True, samesite="Lax")
  ```
  ```js
  res.cookie('refresh_token', refreshToken, { httpOnly: true, secure: true,
    sameSite: 'strict', path: '/auth/refresh', maxAge: THIRTY_DAYS_MS });
  ```
- **Fix:** `HttpOnly`, `Secure`, `SameSite=Lax` (or `Strict`) on every auth cookie; scope the
  path of refresh cookies.
- **Cite:** CWE-1004; CWE-614; OWASP A05:2021 Security Misconfiguration; RFC 6265 §4.1.2.5
  (Secure) and §4.1.2.6 (HttpOnly); OWASP Session Management Cheat Sheet; Flask docs,
  `Response.set_cookie`; Express docs, `res.cookie`.
- **Tool code:** none.

## 8. A06 Vulnerable and Outdated Components

### X-SEC-01 — Dependency change that adds known or unverifiable risk
- **Detect:** in `package.json`, lockfiles, `pyproject.toml` or `requirements*.txt`:
  - advisory output (`npm audit --json`, `pip-audit`, OSV-Scanner) supplied by the user or CI;
    Auditline does not run them (they need the network);
  - mutable sources: `"*"`, `"latest"`, git URLs on a branch, tarball URLs;
  - `--extra-index-url` next to internal package names (dependency confusion: pip takes the
    highest version from any index);
  - deprecated or unmaintained packages used for security work (`pycrypto`, `request`,
    `node-serialize`, `csurf`); a name one letter off a popular package.
- **Default severity:** advisory present: rate its impact on this code path with the rubric (a
  vulnerable function the code never calls is minor), cite the advisory ID. Mutable source:
  minor (C3). Extra index with internal names: major (C2: code execution at install once someone
  publishes the name). Unmaintained security package: minor. Lookalike name: question.
  **Never cite a CVE or GHSA from memory**; without advisory output, a suspicion is a question.
- **Why:** dependencies run with the application's privileges, and at install time.
- WRONG:
  ```json
  "dependencies": { "auth-helpers": "github:someone/auth-helpers#main", "left-pad": "*" }
  ```
  ```text
  --extra-index-url https://pypi.acme.internal/simple
  acme-billing-client>=1.2
  ```
- CORRECT:
  ```json
  "dependencies": { "auth-helpers": "2.4.1", "left-pad": "1.3.0" }
  ```
  ```text
  --index-url https://pypi.acme.internal/simple
  acme-billing-client==1.2.3 --hash=sha256:<digest>
  ```
- **Fix:** pin published versions and commit the lockfile; one index that proxies the public
  one; hash-checking mode; replace unmaintained packages.
- **Cite:** CWE-1104; CWE-1395; CWE-829; OWASP A06:2021 Vulnerable and Outdated Components;
  pip docs, "Secure installs" (hash-checking mode); npm docs, `npm audit`.
- **Tool code:** none in the bundled set (advisory scanners only when the project provides
  their output).

## 9. A07 Identification and Authentication Failures

### PY-SEC-02 · NODE-SEC-02 · TS-SEC-02 — Secret literal in source or in the client bundle
- **Detect:**
  - A literal assigned to or passed as a credential: names with `KEY`, `SECRET`, `TOKEN`,
    `PASSWORD`; `Authorization: Bearer <literal>`; `api_key=`; the key passed to `jwt.sign` /
    `jwt.encode`; Flask/Django `SECRET_KEY`; `user:password@` in a connection string.
  - Prefixes, whatever the name: `AKIA`/`ASIA` (AWS key ID), `ghp_`/`gho_`/`ghs_`/`github_pat_`,
    `xoxb-`/`xoxp-` (Slack), `sk_live_`/`rk_live_`/`whsec_` (Stripe), `sk-`/`sk-ant-`/
    `sk-proj-` (LLM APIs), `AIza` (Google), `-----BEGIN … PRIVATE KEY-----`, `eyJ` (a JWT), any
    `*_live_*` value.
  - A high-entropy literal (20+ characters mixing letters and digits, no spaces) assigned to a
    credential-like name or sent in a header.
  - Decide by use, not prefix: a value sent as a bearer credential from server code is a secret
    even with a `pk_` prefix; Stripe publishable keys used with Stripe.js in the browser are
    public by design.
  - Client side: any secret in browser code, or in an env var inlined into the bundle
    (`NEXT_PUBLIC_*`, `VITE_*`, `REACT_APP_*`). Fallbacks leak too: `os.environ.get("K", "<real
    value>")`, `process.env.K ?? '<real value>'`.
  - ruff S105–S107 match only names containing password, pass, pwd, token or secret, so
    `PAYMENTS_API_KEY = "…"` passes ruff; the model must catch it.
- **Default severity:** blocker for a real credential (X-SEV-04: the leak happens at commit;
  D1–D3 never apply); in a client bundle it is also exposed to every visitor (CWE-200). Major
  for sandbox or test-mode credentials. Not flagged: obvious placeholders (`"changeme"`,
  `"<your-key>"`), publishable keys used client-side, generated test fixtures.
- **Why:** anyone with the repository, an image or the bundle holds the credential, and git
  history keeps it after deletion.
- WRONG:
  ```python
  PAYMENTS_API_KEY = "live_9xQ2mV7kP4tR8wZ1nB6cJ3dF"        # sent as Bearer below
  ```
  ```js
  const SESSION_SIGNING_KEY = 'acme-sessions-2025-prod';
  ```
  ```tsx
  const MAPS_SERVER_KEY = process.env.NEXT_PUBLIC_MAPS_SERVER_KEY;   // inlined into the bundle
  ```
- CORRECT:
  ```python
  PAYMENTS_API_KEY = os.environ["PAYMENTS_API_KEY"]          # fails fast when unset
  ```
  ```js
  const SESSION_SIGNING_KEY = process.env.SESSION_SIGNING_KEY;
  if (!SESSION_SIGNING_KEY) throw new Error('SESSION_SIGNING_KEY is not set');
  ```
  ```tsx
  const res = await fetch('/api/geocode', { method: 'POST', body: JSON.stringify({ address }) });
  // the route handler reads process.env.MAPS_SERVER_KEY on the server
  ```
- **Fix:** environment or secret manager, fail fast when missing; browser calls go through an
  own backend route; **rotate** the leaked value (removing it from the code does not un-leak it).
- **Cite:** CWE-798; CWE-200 (client bundle); OWASP A07:2021 Identification and Authentication
  Failures; OWASP Secrets Management Cheat Sheet; Next.js docs, "Environment Variables"
  (`NEXT_PUBLIC_` values are inlined into the browser bundle); Vite docs, "Env Variables and
  Modes".
- **Tool code:** `[ruff: S105, S106, S107]` (name-based only); JS/TS: none (secret scanners such
  as gitleaks when the project runs them).

### PY-SEC-20 · NODE-SEC-20 · TS-SEC-20 — Authentication or authorization check not awaited
- **Detect:** an async check used in a condition or assigned without `await`: `bcrypt.compare`,
  `argon2.verify`, `canEdit(...)`, `isAdmin(...)`, `verifyToken(...)`, Auth.js `auth()`;
  Python `if not can_edit(user, doc):` where `can_edit` is `async def`. Removed `await` lines
  in the diff count (quote them with `-`).
- **Default severity:** blocker (X-SEV-04): a Promise or coroutine object is always truthy, so
  the check always passes.
- **Why:** the check runs later or never; the branch sees an object, not a boolean.
- WRONG:
  ```js
  const ok = argon2.verify(user.passwordHash, password);
  if (!ok) return reply.code(401).send();
  ```
  ```python
  if not can_edit(user, doc_id):                 # async def can_edit → coroutine, truthy
      raise HTTPException(status_code=403)
  ```
  ```tsx
  if (!isOwner(session, projectId)) throw new Error('Forbidden');   // isOwner is async
  ```
- CORRECT:
  ```js
  if (!(await argon2.verify(user.passwordHash, password))) return reply.code(401).send();
  ```
  ```python
  if not await can_edit(user, doc_id):
      raise HTTPException(status_code=403)
  ```
  ```tsx
  if (!(await isOwner(session, projectId))) throw new Error('Forbidden');
  ```
- **Fix:** `await` the check; enable `no-misused-promises` (type-aware) and mypy
  `truthy-bool`; treat "coroutine … was never awaited" warnings as errors in tests.
- **Cite:** CWE-287; CWE-285; OWASP A07:2021 Identification and Authentication Failures;
  ECMA-262 ToBoolean (objects are truthy); Python docs, "Coroutines and Tasks" and "Truth Value
  Testing".
- **Tool code:** `[typescript-eslint: no-misused-promises, no-floating-promises]`;
  `[mypy: truthy-bool]` (opt-in error code).

### PY-SEC-12 · NODE-SEC-12 — TLS certificate verification disabled
- **Detect:** `verify=False` (requests, httpx), `ssl._create_unverified_context()`,
  `ssl.CERT_NONE`, `check_hostname = False`; Node `rejectUnauthorized: false` (https Agent,
  `tls.connect`, undici, axios agent, pg `ssl` options), `NODE_TLS_REJECT_UNAUTHORIZED = '0'`
  (process-wide).
- **Default severity:** major (C2 defense in depth: a network-position attacker reads and alters
  the traffic, credentials included / R1); minor in tests and local scripts (D3).
- **Why:** encryption without authentication talks securely to whoever answers.
- WRONG:
  ```python
  resp = requests.post(BANK_URL, json=payload, verify=False, timeout=10)
  ```
  ```js
  const pool = new Pool({ connectionString, ssl: { rejectUnauthorized: false } });
  ```
- CORRECT:
  ```python
  resp = requests.post(BANK_URL, json=payload, verify="/etc/ssl/certs/bank-ca.pem", timeout=10)
  ```
  ```js
  const pool = new Pool({ connectionString, ssl: { ca: readFileSync(DB_CA_PATH, 'utf8') } });
  ```
- **Fix:** trust the private CA explicitly instead of disabling verification.
- **Cite:** CWE-295; CWE-297; OWASP A07:2021 Identification and Authentication Failures; Node.js
  docs, `tls.connect` (`rejectUnauthorized`) and `NODE_TLS_REJECT_UNAUTHORIZED`; requests docs,
  "SSL Cert Verification".
- **Tool code:** `[ruff: S501, S323]`; Node: none.

### TS-SEC-27 — Session or refresh token kept in Web Storage
- **Detect:** `localStorage`/`sessionStorage.setItem('token' | 'access_token' | 'refresh_token' |
  'jwt', …)`, `document.cookie = \`token=${t}\`` (a script-set cookie cannot be HttpOnly), a
  persisted auth slice of client state.
- **Default severity:** major for refresh or long-lived tokens (C2 defense in depth: any XSS,
  compromised third-party script or extension reads them / R1); minor for a short-lived access
  token whose refresh token sits in an HttpOnly cookie.
- **Why:** Web Storage is readable by every script on the origin.
- WRONG:
  ```tsx
  localStorage.setItem('refresh_token', data.refreshToken);
  ```
- CORRECT:
  ```tsx
  // server sets: Set-Cookie: refresh_token=…; HttpOnly; Secure; SameSite=Strict; Path=/auth/refresh
  const res = await fetch('/auth/refresh', { method: 'POST', credentials: 'include' });
  const { accessToken } = await res.json();      // kept in memory only
  ```
- **Fix:** HttpOnly cookies for refresh tokens; access tokens in memory.
- **Cite:** CWE-922; CWE-1004; OWASP A07:2021 Identification and Authentication Failures; OWASP
  HTML5 Security Cheat Sheet ("Local Storage"); OWASP Session Management Cheat Sheet.
- **Tool code:** none.

## 10. A08 Software and Data Integrity Failures

### PY-SEC-21 · NODE-SEC-21 — Untrusted data deserialized into objects or code
- **Detect:** Python `pickle.loads/load`, `dill`, `jsonpickle.decode`, `shelve`,
  `yaml.load(…, Loader=yaml.Loader | UnsafeLoader | FullLoader)`, `yaml.unsafe_load`,
  `torch.load(…, weights_only=False)`, `numpy.load(…, allow_pickle=True)`, `joblib.load` on
  uploads, cookies, queue or cache values others can write. Node `node-serialize`
  `unserialize`, `eval('(' + body + ')')` as a JSON parser, js-yaml 3.x `load` (js-yaml 4
  `load` is safe; check the lockfile, otherwise ask).
- **Default severity:** blocker when the bytes come from a request, upload, user-writable store
  or another trust domain (code execution: C1/R1); major behind a visible trusted-user gate
  (D1). Not a finding: files the application wrote to a private path, model files in the
  repository.
- **Why:** these formats rebuild arbitrary objects, and construction runs code.
- WRONG:
  ```python
  prefs = pickle.loads(base64.b64decode(request.cookies["prefs"]))
  config = yaml.load(upload.read(), Loader=yaml.Loader)
  ```
  ```js
  import serialize from 'node-serialize';
  const prefs = serialize.unserialize(req.cookies.prefs);
  ```
- CORRECT:
  ```python
  prefs = Prefs.model_validate_json(request.cookies["prefs"])
  config = yaml.safe_load(upload.read())
  ```
  ```js
  const prefs = PrefsSchema.parse(JSON.parse(req.cookies.prefs));
  ```
- **Fix:** JSON plus schema validation; `yaml.safe_load`; `weights_only=True`; sign data that
  must round-trip and still avoid pickle.
- **Cite:** CWE-502; OWASP A08:2021 Software and Data Integrity Failures; OWASP Deserialization
  Cheat Sheet; Python docs, `pickle` (warning: not secure); PyYAML docs, `safe_load`.
- **Tool code:** `[ruff: S301, S506]`; Node: none.

### PY-SEC-22 · NODE-SEC-22 · TS-SEC-22 — Request body written to a model wholesale (mass assignment)
- **Detect:** `Model(**request.json)`, `setattr(obj, k, v)` over the body,
  `obj.__dict__.update(data)`, `.update(**request.data)`, DRF `fields = "__all__"` on a writable
  serializer; `Object.assign(user, req.body)`, `{ ...row, ...req.body }`,
  `prisma.user.update({ data: req.body })`, `findByIdAndUpdate(id, req.body)`; a server action
  passing `Object.fromEntries(formData)`. A deep merge (`_.merge`, `deepmerge`, a recursive
  helper) of request data enables prototype pollution via `__proto__` or `constructor`.
- **Default severity:** blocker when the target has a privilege, ownership, money or
  verification field (`role`, `is_admin`, `owner_id`, `tenant_id`, `balance`, `email_verified`)
  visible in the model or schema and any user reaches the route (C1/R1); major for prototype
  pollution from a deep merge of request data (medium confidence: the impact depends on what
  reads the polluted keys); a question when the model's fields are not visible.
- **Why:** the client picks which columns change, including the ones the form does not show.
- WRONG:
  ```python
  for field, value in request.get_json().items():
      setattr(current_user, field, value)        # {"role": "admin"} works
  ```
  ```js
  await prisma.user.update({ where: { id: req.user.sub }, data: req.body });
  ```
  ```tsx
  await db.user.update({ where: { id: session.user.id }, data: Object.fromEntries(form) });
  ```
- CORRECT:
  ```python
  data = ProfileUpdate.model_validate(request.get_json())   # display_name, bio only
  current_user.display_name, current_user.bio = data.display_name, data.bio
  ```
  ```js
  const { displayName, bio } = ProfileUpdate.parse(req.body);
  await prisma.user.update({ where: { id: req.user.sub }, data: { displayName, bio } });
  ```
  ```tsx
  const data = ProfileUpdate.parse({ displayName: form.get('displayName'), bio: form.get('bio') });
  await db.user.update({ where: { id: session.user.id }, data });
  ```
- **Fix:** an input schema that lists writable fields; copy fields explicitly; no deep merge of
  request data into shared objects (use `Object.create(null)` or `Map` when merging is needed).
- **Cite:** CWE-915; CWE-1321 (prototype pollution); OWASP A08:2021 Software and Data Integrity
  Failures; OWASP Mass Assignment Cheat Sheet; OWASP API Security Top 10 2023, API3 Broken
  Object Property Level Authorization.
- **Tool code:** none.

## 11. A09 Security Logging and Monitoring Failures

### PY-SEC-23 · NODE-SEC-23 · TS-SEC-23 — Secrets or personal data written to logs or telemetry
- **Detect:** log calls at any level with passwords, tokens, API keys, `Authorization` or
  `Cookie` headers, whole `request.headers`, whole bodies of auth or payment routes, card
  numbers, or bulk PII; objects whose `__repr__`/`toJSON` dumps those fields; in the browser,
  analytics or error-reporting calls with form values, tokens or the session object.
- **Default severity:** major (X-SEV-07, U4). Debug output without secrets or PII is diff hygiene,
  not this rule.
- **Why:** logs are copied to more systems and readers than the database, and are rarely
  access-controlled to the same level.
- WRONG:
  ```python
  logger.info("login attempt email=%s password=%s", email, password)
  ```
  ```js
  req.log.info({ headers: req.headers }, 'webhook received');   // Authorization, Cookie
  ```
  ```tsx
  analytics.track('signup_submitted', formValues);               // includes password
  ```
- CORRECT:
  ```python
  logger.info("login attempt user_id=%s", user.id)
  ```
  ```js
  const app = Fastify({ logger: { redact: ['req.headers.authorization', 'req.headers.cookie'] } });
  req.log.info({ webhookId }, 'webhook received');
  ```
  ```tsx
  analytics.track('signup_submitted', { plan: formValues.plan });
  ```
- **Fix:** log identifiers, not values; configure redaction (Pino `redact`); allowlist the
  properties sent to telemetry.
- **Cite:** CWE-532; OWASP A09:2021 Security Logging and Monitoring Failures; OWASP Logging
  Cheat Sheet ("Data to exclude"); Pino docs, "Redaction".
- **Tool code:** none (`[ruff: T201]` and `[eslint: no-console]` catch the call, not the
  content).

### PY-SEC-24 · NODE-SEC-24 — Security check fails open or its failure leaves no record
- **Detect:** (1) **fail open:** a signature, token or permission check inside `try` whose
  `except`/`catch` logs or ignores and then continues to the protected work; auth middleware
  that calls `next()` on error. (2) **no record:** a new failure path for login, token or
  signature verification, or an authorization denial, that answers `200` or a redirect and logs
  nothing, so the access log cannot show it either. A `401`/`403` already appears in the
  framework's access log (Fastify `logger: true` logs each response's status): not a finding.
- **Default severity:** fail open: blocker (auth bypass, X-SEV-04). No record: minor (C3:
  attacks go unnoticed); a question when a hook or middleware outside the diff may log it.
- **Why:** an exception in the check must deny, and repeated denials are the signal monitoring
  needs.
- WRONG:
  ```python
  try:
      verify_webhook(request.data, request.headers["X-Signature"])
  except Exception:
      logger.debug("bad signature")              # falls through: event processed anyway
  process_event(request.get_json())
  ```
  ```js
  if (!validSignature) return reply.code(200).send();   // forged events dropped with no trace
  ```
- CORRECT:
  ```python
  try:
      verify_webhook(request.data, request.headers["X-Signature"])
  except InvalidSignature:
      logger.warning("webhook signature rejected from %s", request.remote_addr)
      abort(401)
  process_event(request.get_json())
  ```
  ```js
  if (!validSignature) {
    req.log.warn({ event: 'webhook.signature_rejected' }, 'signature rejected');
    return reply.code(401).send();
  }
  ```
- **Fix:** deny inside the handler of a failed check; log security failures at `warning` with
  the event name and source, never the secret.
- **Cite:** CWE-636 (failing open); CWE-778; OWASP A09:2021 Security Logging and Monitoring
  Failures; OWASP Logging Cheat Sheet ("Which events to log").
- **Tool code:** `[ruff: S110, BLE001]` when the fail-open is an `except …: pass`; otherwise none.

## 12. A10 Server-Side Request Forgery

### PY-SEC-25 · NODE-SEC-25 · TS-SEC-25 — Server fetches a URL the caller controls
- **Detect:** a request-derived URL or host reaches `requests`, `httpx`, `urllib.request.urlopen`,
  `aiohttp`, `fetch`, `axios`, `got`, `http.request`, a headless browser `page.goto`, or a
  Next.js route handler, server component or server action. Typical features: webhooks and
  callback URLs, import from URL, link previews, image proxies, PDF rendering. Weak guards:
  `startswith("https://")`, substring host checks, string blocklists, checking the resolved IP
  then fetching by name (DNS rebinding), following redirects after the check (`requests` and
  `fetch` follow them by default).
- **Default severity:** blocker when the caller controls the host and any user reaches it
  (cloud metadata at `169.254.169.254`, internal admin APIs, localhost services: C1/R1); major
  when only the path or query on a fixed host is controlled (C2).
- **Why:** the server's network position and credentials are lent to the caller.
- WRONG:
  ```python
  img = requests.get(request.json["url"], timeout=5)        # http://169.254.169.254/… works
  ```
  ```js
  await fetch(req.body.callbackUrl, { method: 'POST', body: JSON.stringify(event) });
  ```
  ```ts
  export async function GET(req: Request) {
    const src = new URL(req.url).searchParams.get('src') ?? '';
    return fetch(src);                                      // open image proxy
  }
  ```
- CORRECT:
  ```python
  url = urlsplit(request.json["url"])
  if url.scheme != "https" or url.hostname not in ALLOWED_IMAGE_HOSTS:
      abort(400)
  img = requests.get(url.geturl(), timeout=5, allow_redirects=False)
  ```
  ```js
  const url = new URL(req.body.callbackUrl);
  if (url.protocol !== 'https:') return reply.code(400).send();
  // resolve, reject private, loopback and link-local ranges (net.BlockList), connect to that
  // IP or send through an egress proxy that enforces the same rule; redirect: 'error'
  ```
  ```ts
  const src = new URL(new URL(req.url).searchParams.get('src') ?? '', 'https://invalid.');
  if (src.protocol !== 'https:' || !ALLOWED_HOSTS.has(src.hostname)) {
    return new Response(null, { status: 400 });
  }
  return fetch(src, { redirect: 'error' });
  ```
- **Fix:** host allowlist; when arbitrary hosts are a feature (webhooks), resolve and block
  private ranges at connect time or use an egress proxy; disable redirects; do not return the
  raw response.
- **Cite:** CWE-918; OWASP A10:2021 Server-Side Request Forgery; OWASP Server Side Request
  Forgery Prevention Cheat Sheet; Python docs, `ipaddress` (`is_private`, `is_loopback`,
  `is_link_local`); Node.js docs, `net.BlockList`.
- **Tool code:** `[ruff: S310]` (`urlopen` scheme audit only); none for requests or fetch.

## 13. Do not flag

These add to the noise table in `refs/severity-and-output-format.md` §6.

| Pattern | Why it is not a finding |
|---|---|
| No rate limiting, helmet, CSP or HSTS in the diff | absence of a control: question at most (X-SEV-09) |
| `target="_blank"` without `rel="noopener"` | current browsers imply `noopener` for `_blank` (HTML Standard) |
| CSRF on an API authenticated only by an `Authorization` header | browsers do not attach that header cross-site |
| `random` / `Math.random` for jitter, sampling, shuffling, test data | no security value depends on it |
| md5/sha1 for checksums, cache keys or ETags (`usedforsecurity=False`) | not a security use; drop ruff S324 with that reason |
| `jwtDecode` in the browser to show claims | display only; the server verifies |
| Stripe `pk_` keys, Firebase web config, Sentry DSN in client code | public by design |
| `Access-Control-Allow-Origin: *` without credentials on a public API | no ambient credentials are sent |
| ruff S608 where every interpolated value is a constant or allowlisted identifier | not request-controlled; drop with that reason |
| `subprocess.run([...])` with a constant list and no shell (ruff S603) | audit-only code; no input reaches it |
| `0.0.0.0` bind in a container entrypoint (ruff S104) | the container network is the boundary |
| `dangerouslySetInnerHTML` with a constant or unchanged `DOMPurify.sanitize` output | nothing user-controlled is rendered raw |
| Secrets in `.env.example` or tests that are obvious placeholders | nothing real is leaked |

## 14. Security-only mode

With `--security-only`, load this ref and the `-SEC-` items of each language checklist; nothing
else is triaged. Every rule here has a `-SEC-` ID, so information exposure in error responses
(PY/NODE-SEC-18) and secrets in logs (PY/NODE/TS-SEC-23) are reported, while debug prints
without secrets, swallowed non-security exceptions and performance issues are not. Linter codes
kept: ruff `S*`, ESLint security-plugin rules, `no-eval`, `no-implied-eval`, `no-new-func`,
`react/no-danger`, `react/jsx-no-script-url`, `no-misused-promises` when it flags an auth check.
The verdict covers security findings only.
