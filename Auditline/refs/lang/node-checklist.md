# Node checklist

Sources: Node.js docs (ESM, `process`, `events`, `http`, `util`); ECMAScript and MDN; Express,
Fastify, Pino, Prisma and BullMQ docs; RFC 9457, RFC 9700; OWASP cheat sheets; Docker and
Kubernetes docs as cited per rule. Distilled from CodeWriter's Node refs (see the provenance
comment on each section).

## Contents

1. How to use this checklist
2. Naming and modules
3. TypeScript and types
4. Web frameworks
5. Security
6. Error handling
7. Async patterns
8. Logging and observability
9. Config and secrets
10. Testing
11. Performance
12. Database and ORM
13. Background jobs and queues
14. API design
15. DevOps and containers

## 1. How to use this checklist

- **Scope.** Load this file for server-side `.js`, `.mjs`, `.cjs` and `.ts` files and for
  `package.json`, together with at most three topic refs. The topic refs own the rules shared by
  all languages; this file names which of them apply to each area and adds what is specific to
  Node. Each section below corresponds to one CodeWriter ref. React and browser code use the
  TypeScript/React checklist.
- **Tools first.** Run `eslint` and `tsc --noEmit` (project config first). Report their hits with
  `source: eslint|tsc`. Rules that need type information (`no-floating-promises`,
  `no-misused-promises`) only run with typed linting; if the project has none, the model covers them
  (`NODE-COR-10`, `NODE-ERR-08`).
- **Rule IDs.** `NODE-<CAT>-NN`. Numbers 01-49 are defined in the topic refs and are shared across
  languages; numbers from 51 up are defined in the language checklists, and the same number is the
  same concept in all of them. `NODE-OPS-NN` covers Dockerfiles and deployment files and triages
  with maintainability.
- **Absent controls are questions.** Helmet, rate limiting, a JWT `algorithms` list and request
  validation that the diff does not show are at most a question (X-SEV-09). Report them as findings
  only when the shown code makes an attack work.
- **Not flagged.** CodeWriter rules about how to write code (Fastify plugins, Prisma versus
  Drizzle, `#private` fields, named exports, `async/await` over `.then`, a single `env` object,
  `pino-pretty` set-up, PM2 clustering, OpenAPI generation, `X-Request-Id` and rate-limit headers)
  are design or style choices. Report them only when the project states the convention and the
  diff breaks it.

## 2. Naming and modules

<!-- provenance: CodeWriter/node/refs/naming-and-modules.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-MAINT-01` (unused imports), `NODE-MAINT-02` (misleading names, units),
`NODE-MAINT-06` (magic values).

### NODE-COR-62 — Relative ESM import without a file extension
- **Detect:** in a package with `"type": "module"` (or `.mjs` files) that Node runs directly:
  `import { x } from './user-service'` or `'./utils'` or a directory import. A bundler or
  `vitest` resolves these, so tests pass.
- **Default severity:** major (C2/R1: `ERR_MODULE_NOT_FOUND` when Node starts the service);
  blocker when the module is on the start-up path of the entry point.
- **Why:** Node's ESM loader does not guess extensions or `index.js`.
- WRONG:
  ```js
  import { findUser } from './user-service';        // ERR_MODULE_NOT_FOUND under `node server.js`
  ```
- CORRECT:
  ```js
  import { findUser } from './user-service.js';     // in TypeScript source too: the emitted file is .js
  ```
- **Fix:** write the extension (`.js` even for `.ts` sources), or compile with a tool that rewrites
  specifiers.
- **Cite:** Node.js docs, "ECMAScript modules: Mandatory file extensions"; TypeScript handbook,
  "Modules - Theory" (`moduleResolution: nodenext`).
- **Tool code:** `[eslint: import/extensions]`, `[tsc: TS2835]`.

### NODE-COR-63 — CommonJS globals used in an ES module
- **Detect:** `require(...)`, `module.exports`, `exports.x`, `__dirname` or `__filename` in a
  `.mjs` file or a `"type": "module"` package.
- **Default severity:** major (C2/R1: `ReferenceError` on the path that reaches it); blocker at
  module top level of the entry path.
- **Why:** those names exist only in CommonJS wrappers.
- WRONG:
  ```js
  const path = require('node:path');
  const cfgPath = path.join(__dirname, 'config.json');   // ReferenceError in ESM
  ```
- CORRECT:
  ```js
  import path from 'node:path';
  const cfgPath = path.join(import.meta.dirname, 'config.json');    // Node 20.11+; else fileURLToPath(import.meta.url)
  ```
- **Fix:** `import`; `import.meta.dirname` / `import.meta.filename` (20.11+) or `fileURLToPath`;
  `createRequire(import.meta.url)` for a CommonJS-only package.
- **Cite:** Node.js docs, "ECMAScript modules: Differences between ES modules and CommonJS".
- **Tool code:** `[eslint: no-undef]` (with ESM globals), `[eslint: import/no-commonjs]`.

### NODE-MAINT-52 — Autofixable style (nit bucket)
- **Detect:** only what a tool reports: import order, `import type` for type-only imports,
  quote or semicolon style, `UPPER_SNAKE_CASE` constants, default versus named export where the
  project config sets a rule.
- **Default severity:** nit (X-SEV-08); collapse to a count when the tool ran; list at most five.
- **Why:** reader cost only; the formatter or `--fix` repairs it.
- WRONG:
  ```ts
  import { User } from './types.js';                  // used only as a type
  import fs from 'node:fs';
  import express from 'express';
  ```
- CORRECT:
  ```ts
  import fs from 'node:fs';

  import express from 'express';

  import type { User } from './types.js';
  ```
- **Fix:** `eslint --fix`, `prettier --write`.
- **Cite:** TypeScript docs, `verbatimModuleSyntax`; typescript-eslint, `consistent-type-imports`.
- **Tool code:** `[typescript-eslint: consistent-type-imports]`, `[eslint: import/order, sort-imports]`.

## 3. TypeScript and types

<!-- provenance: CodeWriter/node/refs/typescript-and-types.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-MAINT-08` (TypeScript files: `any`, `as T` on external data, `@ts-ignore`, `!`), `NODE-COR-04` (absent value dereferenced).

### NODE-MAINT-53 — Compiler or linter strictness weakened
- **Detect:** in `tsconfig*.json`: `"strict": false`, `"noImplicitAny": false`,
  `"strictNullChecks": false`, `"noUncheckedIndexedAccess": false`, `"skipLibCheck"` added to hide
  your own errors; in ESLint config: a rule turned `off`, a new `ignores` entry for source files;
  inline `// @ts-nocheck`, a blanket `/* eslint-disable */`.
- **Default severity:** minor; major when the change silences an error the diff itself introduces.
- **Why:** the safety net shrinks with no visible reason.
- WRONG:
  ```json
  { "compilerOptions": { "strict": true, "strictNullChecks": false } }
  ```
- CORRECT:
  ```json
  { "compilerOptions": { "strict": true } }
  ```
- **Fix:** keep the flag on and fix the errors; scope a necessary exception to one file with a
  comment that explains why.
- **Cite:** TypeScript docs, "TSConfig Reference: strict"; typescript-eslint, `ban-ts-comment`.
- **Tool code:** `[typescript-eslint: ban-ts-comment]` for inline directives; none for config
  changes.

### NODE-COR-64 — Implicit numeric enum values that are stored or sent
- **Detect:** `enum Status { Active, Inactive }` (no initializers) whose numeric values are
  written to a database, a queue, a cache or an API response; members reordered or inserted in
  the diff.
- **Default severity:** major (C1/R2: reordering or inserting a member silently changes the meaning
  of persisted rows); minor if values never leave the process.
- **Why:** members are numbered by position (`Active = 0`).
- WRONG:
  ```ts
  enum Status { Active, Suspended, Closed }        // "Suspended" inserted: Closed was 1, is now 2
  await db.insert({ status: Status.Closed });
  ```
- CORRECT:
  ```ts
  const Status = { Active: 'active', Suspended: 'suspended', Closed: 'closed' } as const;
  type Status = (typeof Status)[keyof typeof Status];
  ```
- **Fix:** string values (`as const` object or a string enum), or explicit initializers that are
  never renumbered.
- **Cite:** TypeScript handbook, "Enums" (numeric enums, auto-incremented members);
  typescript-eslint, `prefer-enum-initializers`.
- **Tool code:** `[typescript-eslint: prefer-enum-initializers]`.

### NODE-COR-53 — Syntax or API newer than the supported Node version
- **Detect:** the diff uses `structuredClone` (Node 17), global `fetch` (18),
  `Array.prototype.toSorted` / `toReversed` (20), `import.meta.dirname` (20.11), `Object.groupBy`
  (21), `Promise.withResolvers` (22), `--experimental-strip-types`, while `engines.node`,
  `.nvmrc`, the Dockerfile base image or the CI matrix allows an older Node.
- **Default severity:** blocker when the declared range includes a Node that lacks the API
  (`TypeError` or `SyntaxError` on that path, a broken supported-version contract); minor when
  every environment shown already runs the newer version and `engines` is stale.
- **Why:** it works on the developer's Node and fails on the supported one.
- WRONG:
  ```js
  // package.json: "engines": { "node": ">=18" }
  const sorted = users.toSorted((a, b) => a.age - b.age);     // Node 20+
  ```
- CORRECT:
  ```js
  const sorted = [...users].sort((a, b) => a.age - b.age);    // or raise engines and the CI matrix together
  ```
- **Fix:** raise `engines` and the CI matrix together, or use the compatible form.
- **Cite:** Node.js docs, per-API "History" tables; MDN, browser and runtime compatibility tables;
  npm docs, `engines`.
- **Tool code:** `[eslint: n/no-unsupported-features/es-builtins, n/no-unsupported-features/node-builtins]`.

## 4. Web frameworks

<!-- provenance: CodeWriter/node/refs/web-frameworks.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-COR-01` (module-level per-request state), `NODE-ERR-08` (async Express 4
handler not wrapped), `NODE-ERR-05` (error handler with three parameters), `NODE-OPS-05`
(shutdown). Not flagged: choice of framework and Fastify plugin structure.

### NODE-COR-65 — Middleware registered after the routes it must guard
- **Detect:** in the order of `app.use(...)` / `app.register(...)` / `app.addHook(...)` calls: a
  body parser (`express.json()`), `cors()`, `helmet()`, an auth or rate-limit middleware, or a
  request-id hook registered **after** the routes it should apply to; an error-handling middleware
  registered **before** the routes. Express runs middleware in registration order.
- **Default severity:** blocker when the late middleware is authentication or authorization (routes
  above it are open, X-SEV-04 class); major otherwise (`req.body` is `undefined`, CORS headers
  missing, errors unhandled). When it is authentication or authorization, file it as `NODE-SEC-04`
  (broken access control, CWE-862) so a `--security-only` review keeps it; this rule is for the rest.
- **Why:** a route registered before a middleware never runs it.
- WRONG:
  ```js
  app.get('/admin/users', listUsers);
  app.use(requireAuth);                      // too late: /admin/users is already open
  app.use(express.json());
  ```
- CORRECT:
  ```js
  app.use(express.json());
  app.use(requireAuth);
  app.get('/admin/users', listUsers);
  app.use(errorHandler);                     // last
  ```
- **Fix:** register parsers and security first, routes next, the error handler last; in Fastify,
  scope hooks to a plugin that contains the routes.
- **Cite:** Express docs, "Using middleware" (order of middleware loading is important);
  Fastify docs, "Hooks" and "Encapsulation"; CWE-862.
- **Tool code:** none.

### NODE-PERF-54 — Response serialized by hand in Fastify
- **Detect:** `reply.send(JSON.stringify(data))`, or a route with no response `schema` returning
  large objects.
- **Default severity:** nit; minor on a hot route with large payloads.
- **Why:** it bypasses Fastify's compiled serializer and, with a string body, the JSON content
  type must then be set by hand.
- WRONG:
  ```js
  app.get('/orders', async (req, reply) => reply.send(JSON.stringify(await listOrders())));
  ```
- CORRECT:
  ```js
  app.get('/orders', { schema: { response: { 200: OrderListSchema } } }, async () => listOrders());
  ```
- **Fix:** return the object and declare a response schema.
- **Cite:** Fastify docs, "Validation and Serialization" (response schema serialization).
- **Tool code:** none.

## 5. Security

<!-- provenance: CodeWriter/node/refs/security-web.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-SEC-01` SQL, `-03` path, `-04` ownership, `-06` CSRF, `-09` CORS, `-11` JWT,
`-16` HTML, `-17` client-supplied price, `-19` cookie flags, `-21` deserialization, `-22` mass
assignment, `-25` SSRF, `X-SEC-01` dependencies. Helmet, rate limiting and Zod on every route are
questions when absent (X-SEV-09, severity ref §6). Not flagged: choice of authentication
architecture.

### NODE-SEC-53 — Refresh token not rotated, not revocable, or stored in clear
- **Detect:** a refresh endpoint that issues a new access token and returns the **same** refresh
  token; no revocation on logout or on reuse of an old token; refresh tokens stored raw in the
  database (a database leak is then a session leak); a refresh token with no expiry.
- **Default severity:** major (C2/R1); blocker if the token never expires and is also in a cookie
  without `HttpOnly` (the pair is a durable account takeover).
- **Why:** a stolen refresh token stays valid for ever and cannot be told from the real user's.
- WRONG:
  ```js
  app.post('/auth/refresh', async (req, reply) => {
    const { sub } = jwt.verify(req.cookies.refresh, REFRESH_SECRET);
    return { access: jwt.sign({ sub }, ACCESS_SECRET, { expiresIn: '15m' }) };   // same refresh token, no rotation
  });
  ```
- CORRECT:
  ```js
  const row = await db.refreshTokens.findByHash(sha256(req.cookies.refresh));
  if (!row || row.revokedAt) { await db.refreshTokens.revokeFamily(row?.familyId); throw unauthorized(); }  // reuse
  await db.refreshTokens.revoke(row.id);
  const next = await db.refreshTokens.issue({ familyId: row.familyId, userId: row.userId });
  ```
- **Fix:** rotate on every use; store only a hash; revoke the whole family when an old token is
  presented again.
- **Cite:** RFC 9700 (OAuth 2.0 Security BCP) §4.14 (refresh token protection); OWASP Session
  Management Cheat Sheet; CWE-613.
- **Tool code:** none.

### NODE-SEC-54 — Login or reset reveals whether an account exists
- **Detect:** login that returns "no such user" for an unknown email and "wrong password" for a
  known one (different message, status code or timing); a password-reset request that answers
  "email not found". Signup rejecting a taken email is **not** this rule (severity ref §6).
- **Default severity:** minor (C2/R1, CWE-204); no finding when the diff does not touch the login
  or reset path.
- **Why:** attackers learn which emails have accounts and target them.
- WRONG:
  ```js
  if (!user) return reply.code(404).send({ error: 'No account with that email' });
  if (!(await bcrypt.compare(password, user.hash))) return reply.code(401).send({ error: 'Wrong password' });
  ```
- CORRECT:
  ```js
  const ok = user && await bcrypt.compare(password, user.hash);
  if (!ok) return reply.code(401).send({ error: 'Invalid email or password' });
  ```
- **Fix:** one message and one status for both cases; equalize the work (hash a dummy password when
  the user is missing).
- **Cite:** OWASP Authentication Cheat Sheet, "Authentication and error messages"; CWE-204; OWASP
  ASVS 4.0.3 V2.2.
- **Tool code:** none.

## 6. Error handling

<!-- provenance: CodeWriter/node/refs/error-handling-web.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-ERR-05` (status codes, RFC 9457 shape, four-argument handler), `NODE-SEC-18`
(stack trace or `err.message` in a response, reported once there), `NODE-ERR-03` (lost cause),
`NODE-ERR-01` (swallowed), `NODE-ERR-02` (broad catch). Not flagged: an `AppError` hierarchy and
a single central handler are design choices.

### NODE-ERR-52 — `schema.parse()` of client input with the error left unmapped
- **Detect:** `Schema.parse(req.body)` (Zod) in a handler, an action or an event handler with no
  `try`/`catch` and no framework hook that maps `ZodError` to 400/422; in the browser, `parse` on
  an API response outside a `try`.
- **Default severity:** minor (C3: bad input becomes a 500); major when it is the only validation
  on a public route and 500s page the on-call.
- **Why:** `parse` throws; `safeParse` returns a result the code must handle.
- WRONG:
  ```js
  app.post('/orders', async (req) => {
    const body = OrderSchema.parse(req.body);      // ZodError → 500
    return createOrder(body);
  });
  ```
- CORRECT:
  ```js
  app.post('/orders', async (req, reply) => {
    const parsed = OrderSchema.safeParse(req.body);
    if (!parsed.success) return reply.code(422).type('application/problem+json')
      .send({ type: 'about:blank', title: 'Invalid order', status: 422, errors: parsed.error.flatten() });
    return createOrder(parsed.data);
  });
  ```
- **Fix:** `safeParse` and return 400/422, or register one error handler that maps `ZodError`.
- **Cite:** Zod docs, "Basic usage" (`parse` throws, `safeParse` returns); RFC 9457; RFC 9110 §15.5.
- **Tool code:** none.

### NODE-ERR-54 — `uncaughtException` or `unhandledRejection` handler that keeps running
- **Detect:** `process.on('uncaughtException', (err) => { log(err); })` or
  `process.on('unhandledRejection', ...)` that logs and returns without exiting or starting a
  shutdown.
- **Default severity:** major (C2/R1: the process continues in an undefined state: half-written
  data, leaked handles, stuck locks).
- **Why:** after an uncaught exception the process cannot be trusted to be consistent.
- WRONG:
  ```js
  process.on('uncaughtException', (err) => { logger.error(err); });   // carries on
  ```
- CORRECT:
  ```js
  process.on('uncaughtException', (err) => {
    logger.fatal({ err }, 'uncaught exception');
    server.close(() => process.exit(1));                          // let the orchestrator restart it
    setTimeout(() => process.exit(1), 10_000).unref();
  });
  ```
- **Fix:** log, close the server with a deadline and exit non-zero.
- **Cite:** Node.js docs, `process` event `'uncaughtException'` (it is not safe to resume normal
  operation after it).
- **Tool code:** none.

## 7. Async patterns

<!-- provenance: CodeWriter/node/refs/async-patterns.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-COR-10` (floating promise, `forEach(async)`, `return` inside `try`),
`NODE-ERR-08` (background rejection), `NODE-ERR-04` (no `AbortSignal.timeout`), `NODE-ERR-06`
(`pipe` without `pipeline`), `NODE-PERF-02` (`*Sync`), `NODE-PERF-03` (serial awaits),
`NODE-PERF-04` (unbounded `Promise.all`), `NODE-ERR-01` (`allSettled` results unread). Not
flagged: `async/await` versus `.then()`.

### NODE-ERR-53 — EventEmitter listener added per call and never removed
- **Detect:** `emitter.on(...)`, `process.on(...)` or `socket.on(...)` inside a request handler,
  a loop or a function called per request, with no matching `off` / `once` / `removeListener`; a
  `MaxListenersExceededWarning` in logs or tests; `setMaxListeners(0)` added to silence it.
- **Default severity:** major (C2/R1: memory and CPU grow with each call, and every listener fires
  on every later event).
- **Why:** listeners live as long as the emitter; the closure keeps what it captured alive.
- WRONG:
  ```js
  app.get('/stream/:id', (req, reply) => {
    bus.on('update', (msg) => reply.raw.write(msg));      // one more listener per request, forever
  });
  ```
- CORRECT:
  ```js
  app.get('/stream/:id', (req, reply) => {
    const onUpdate = (msg) => reply.raw.write(msg);
    bus.on('update', onUpdate);
    req.raw.on('close', () => bus.off('update', onUpdate));
  });
  ```
- **Fix:** remove the listener when the request or connection ends; `once` where it fires once.
- **Cite:** Node.js docs, `events` ("Possible EventEmitter memory leak", `emitter.off`); CWE-401.
- **Tool code:** none.

### NODE-COR-61 — Check-then-use on the filesystem
- **Detect:** `if (fs.existsSync(p)) { fs.readFileSync(p) }`, `await fs.access(p)` followed by
  `open`/`unlink`, `if (!exists) writeFile(p)` where another process or request can change the
  path between the two calls.
- **Default severity:** minor (C2/R2); major when the path is shared (an upload or temp directory)
  and the file is trusted afterwards.
- **Why:** the file can appear, vanish or be replaced between the check and the use.
- WRONG:
  ```js
  if (!fs.existsSync(lockPath)) {
    fs.writeFileSync(lockPath, String(process.pid));      // two processes can both pass the check
  }
  ```
- CORRECT:
  ```js
  try {
    fs.writeFileSync(lockPath, String(process.pid), { flag: 'wx' });   // fails if it exists
  } catch (err) {
    if (err.code === 'EEXIST') throw new Error('already running', { cause: err });
    throw err;
  }
  ```
- **Fix:** attempt the operation and handle the error; the `wx` flag for exclusive creation;
  `fs.mkdtemp` for temporary directories.
- **Cite:** CWE-367; Node.js docs, `fs.access` ("Using `fs.access()` to check for the accessibility
  of a file before calling `fs.open()`... is not recommended") and file system flags (`wx`).
- **Tool code:** none.

## 8. Logging and observability

<!-- provenance: CodeWriter/node/refs/logging-observability.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-DIFF-01` (`console.log`), `NODE-SEC-23` (secrets and PII in logs; `pino.redact`
is the fix), `NODE-ERR-03` (log `err` object, not `err.message`). Not flagged: choice of logger,
`pino-pretty` configuration in development, child-logger and correlation-id design,
OpenTelemetry set-up.

### NODE-COR-66 — Logger called with the fields in the wrong position
- **Detect:** Pino (and Bunyan) take the object **first**: `log.info('user logged in', { userId })`
  drops `{ userId }`; `log.error('failed', err)` drops the error. Winston and `console` accept the
  object second, so check which logger the project uses.
- **Default severity:** minor (C3: the fields the on-call needs are missing from the log);
  major if the dropped field is the error on a failure path (the stack trace is lost).
- **Why:** extra arguments after a string are used only as `%s` substitutions.
- WRONG:
  ```js
  req.log.info('order created', { orderId, userId });         // pino: fields silently dropped
  req.log.error('charge failed', err);                         // no stack
  ```
- CORRECT:
  ```js
  req.log.info({ orderId, userId }, 'order created');
  req.log.error({ err }, 'charge failed');
  ```
- **Fix:** object first, message second; the error under the `err` key.
- **Cite:** Pino docs, "API: logger" (`logger.info([mergingObject], [message], [...interpolationValues])`);
  Pino docs, "Pino standard serializers" (`err`).
- **Tool code:** none.

### NODE-MAINT-58 — Log message built by interpolation
- **Detect:** `` log.info(`user ${id} paid ${amount}`) ``, `log.info('x ' + y)`.
- **Default severity:** nit; minor on a hot path.
- **Why:** the values cannot be queried as fields, and the string is built even when the level is
  off.
- WRONG:
  ```js
  req.log.info(`payment ${paymentId} captured for ${userId}`);
  ```
- CORRECT:
  ```js
  req.log.info({ paymentId, userId }, 'payment captured');
  ```
- **Fix:** bindings first.
- **Cite:** Pino docs, "Child loggers" and "API: logger"; OWASP Logging Cheat Sheet.
- **Tool code:** none.

### NODE-MAINT-59 — Library code creates or configures a logger
- **Detect:** in a module meant to be imported by others: `pino()` / `winston.createLogger()` at
  top level with transports, or `process.on` log hooks.
- **Default severity:** minor (C3: the application cannot control the output).
- **Why:** only the application decides destinations and levels.
- WRONG:
  ```js
  // lib/client.js
  export const logger = pino({ level: 'debug', transport: { target: 'pino-pretty' } });
  ```
- CORRECT:
  ```js
  // lib/client.js
  export function createClient({ logger = { debug() {}, info() {}, error() {} } } = {}) { /* ... */ }
  ```
- **Fix:** accept an optional `logger` parameter with a no-op default.
- **Cite:** Node.js docs, `diagnostics_channel` (library-neutral diagnostics); OpenTelemetry docs,
  "Libraries" (instrumentation for libraries must not own the exporter).
- **Tool code:** none.

### NODE-PERF-55 — Unbounded metric label cardinality
- **Detect:** `counter.labels({ user: userId })`, a histogram labelled with the raw URL path (ids
  in it), email, request id or error message (`prom-client`).
- **Default severity:** major (C2/R1: each value is a new time series).
- **Why:** series count is the product of label values.
- WRONG:
  ```js
  httpRequests.inc({ path: req.url, user: req.user.id });        // /orders/1, /orders/2, ...
  ```
- CORRECT:
  ```js
  httpRequests.inc({ route: req.routeOptions.url, status: reply.statusCode });
  ```
- **Fix:** route template and status only; ids go to logs and traces.
- **Cite:** Prometheus docs, "Instrumentation" and "Metric and label naming"; prom-client README;
  CWE-770.
- **Tool code:** none.

## 9. Config and secrets

<!-- provenance: CodeWriter/node/refs/config-and-secrets.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-SEC-02` (hardcoded secret, a secret default such as
`process.env.JWT_SECRET ?? 'dev-secret'`), `NODE-SEC-23` (secrets in logs and errors),
`NODE-SEC-24` (`NODE_ENV` used to switch security behavior: a missing or mistyped value fails open),
`NODE-SEC-09` (`origin: '*'`), `X-DIFF-06` (`.env` committed), `NODE-COR-04` and `NODE-COR-05`
(an unset or `"false"` variable). Not flagged: a Zod-validated `env` module, `.env.example`, and
`Secret` wrapper types are recommended patterns; their absence is a design choice.

### NODE-COR-67 — Environment value used without parsing
- **Detect:** `Number(process.env.PORT)` or `parseInt(process.env.TIMEOUT)` used directly
  (`undefined` gives `NaN`, `''` gives `0`); `process.env.X === true`; `if (process.env.FLAG)`
  for a boolean (`COR-05`); a numeric value never range-checked, used as a limit or a timeout.
- **Default severity:** major when `NaN` or `0` reaches a timeout, limit, port or retry count
  (C2/R1: no timeout, no limit); minor otherwise.
- **Why:** environment values are strings or missing, and `Number` turns both into numbers that look
  valid.
- WRONG:
  ```js
  const timeoutMs = Number(process.env.UPSTREAM_TIMEOUT_MS);       // unset → NaN → no timeout in many clients
  server.listen(Number(process.env.PORT));                          // unset → NaN
  ```
- CORRECT:
  ```js
  const Env = z.object({ UPSTREAM_TIMEOUT_MS: z.coerce.number().int().positive().default(5000) });
  const { UPSTREAM_TIMEOUT_MS } = Env.parse(process.env);           // fails at start-up if invalid
  ```
- **Fix:** parse and validate all variables once at start-up and fail fast.
- **Cite:** MDN, `Number()` (`Number(undefined)` is `NaN`, `Number('')` is `0`); Twelve-Factor App,
  III Config.
- **Tool code:** none.

## 10. Testing

<!-- provenance: CodeWriter/node/refs/testing-web.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-TEST-01` to `NODE-TEST-08` (untested logic, vacuous assertions, over-mocking,
flaky waits and fixed ports, `.only`/`.skip`, shared state and mocks not reset). Not flagged:
Vitest versus Jest, coverage thresholds, snapshot scope, and AAA layout.

### NODE-TEST-52 — Async test mixing a `done` callback and a promise
- **Detect:** `it('...', async (done) => {...})`, or a test that takes `done` and also returns a
  promise; `done` called inside a `try` whose `catch` swallows the assertion error.
- **Default severity:** minor; major if it is the only test of the behavior (an assertion failure
  becomes a timeout or is lost).
- **Why:** Jest errors on the combination, and in other runners an assertion thrown in a callback
  never reaches the test.
- WRONG:
  ```js
  it('emits ready', async (done) => {
    server.on('ready', () => { expect(server.port).toBeGreaterThan(0); done(); });
    await server.start();
  });
  ```
- CORRECT:
  ```js
  it('emits ready', async () => {
    const ready = once(server, 'ready');
    await server.start();
    await ready;
    expect(server.port).toBeGreaterThan(0);
  });
  ```
- **Fix:** use `async`/`await` (and `events.once`); no `done` in new tests.
- **Cite:** Jest docs, "Testing Asynchronous Code"; Node.js docs, `events.once`.
- **Tool code:** `[eslint: jest/no-done-callback]`.

## 11. Performance

<!-- provenance: CodeWriter/node/refs/performance-web.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-PERF-02` (`*Sync`, CPU on the event loop), `NODE-PERF-05` (whole file or body in
memory, unbounded cache), `NODE-PERF-08` (a client or pool per request), `NODE-COR-16` (cache key
missing a dimension), `NODE-COR-60` (process-local cache), `NODE-PERF-54` (manual stringify). Not
flagged: PM2 clustering, `clinic.js` profiling, caching layers and stale-while-revalidate design.

### NODE-COR-60 — Process-local cache invalidated only in the process that wrote
- **Detect:** a module-level `Map`, `lru-cache` or memoized function holding data other processes
  can change, with the write path deleting or clearing the entry, in a service run as several
  processes (PM2 cluster mode, `cluster`, several containers or replicas shown in the Dockerfile,
  compose or manifest).
- **Default severity:** major (C2/R1: other processes serve the old value until restart). Question
  if the process count is not visible.
- **Why:** each process has its own memory, so the invalidation reaches one of N.
- WRONG:
  ```js
  const plans = new LRUCache({ max: 500 });
  export async function updatePlan(id, fields) {
    await db.plans.update(id, fields);
    plans.delete(id);                                  // this process only
  }
  ```
- CORRECT:
  ```js
  export async function getPlan(id) {
    const version = (await redis.get('plans:version')) ?? 0;     // shared; bump the version on write
    return cached(`plan:${id}:v${version}`, () => db.plans.get(id));
  }
  ```
- **Fix:** a shared cache (Redis) with a version key or short TTL, or no cache on mutable data.
- **Cite:** Node.js docs, `cluster` (workers are separate processes); `lru-cache` README.
- **Tool code:** none.

### NODE-OPS-08 — `keepAliveTimeout` shorter than the load balancer's idle timeout
- **Detect:** a server that sets `keepAliveTimeout` (or leaves Node's default of 5 s) behind a load
  balancer whose idle timeout is longer (an AWS ALB defaults to 60 s); `server.keepAliveTimeout`
  assigned a value below the proxy's.
- **Default severity:** minor; major when 502 or `ECONNRESET` errors are already reported in the
  change description.
- **Why:** Node closes an idle connection the proxy still considers open, and the proxy's next
  request on it fails.
- WRONG:
  ```js
  const server = http.createServer(app);                   // keepAliveTimeout defaults to 5 s; ALB idle timeout is 60 s
  ```
- CORRECT:
  ```js
  server.keepAliveTimeout = 65_000;                          // longer than the ALB idle timeout
  server.headersTimeout = 66_000;                            // greater than keepAliveTimeout
  ```
- **Fix:** set `keepAliveTimeout` above the proxy idle timeout and `headersTimeout` above that.
- **Cite:** Node.js docs, `server.keepAliveTimeout` (default 5000 ms); AWS docs, "Application Load
  Balancer: idle timeout" (default 60 s).
- **Tool code:** none.

## 12. Database and ORM

<!-- provenance: CodeWriter/node/refs/database-and-orm.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-PERF-01` (N+1, `include`), `NODE-PERF-05` (no `take`, no `select`),
`NODE-PERF-07` (full scan, deep offset), `NODE-PERF-08` (a pool per request), `NODE-ERR-07`
(multi-step write without `$transaction`), `NODE-SEC-01` (raw SQL), `NODE-OPS-06` (migrations in
the deploy path). Not flagged: Prisma versus Drizzle.

### NODE-COR-68 — Query on a soft-deleted model without the `deletedAt` filter
- **Detect:** the schema or model has a `deletedAt` (or `isDeleted`) column, and a new
  `findMany` / `findFirst` / `count` / join on that model has no `deletedAt: null` filter and no
  client extension or view that adds it.
- **Default severity:** major (C2/R1: deleted records are shown, counted or billed; for personal
  data, deleted data is still disclosed). Medium confidence unless the extension is visible.
- **Why:** the ORM does not know a row is "deleted".
- WRONG:
  ```js
  const projects = await prisma.project.findMany({ where: { ownerId } });     // includes deleted
  ```
- CORRECT:
  ```js
  const projects = await prisma.project.findMany({ where: { ownerId, deletedAt: null } });
  ```
- **Fix:** add the filter, or enforce it in one place (a Prisma client extension or a view).
- **Cite:** Prisma docs, "Client extensions" (query component); CWE-212 (improper removal of
  sensitive information).
- **Tool code:** none.

### NODE-COR-69 — "First" row taken without a deterministic order
- **Detect:** `findFirst`, `LIMIT 1`, `.first()` or `rows[0]` on a query that can match several
  rows and has no `orderBy` / `ORDER BY` that makes one row correct (latest, highest, oldest).
- **Default severity:** major when the choice affects money, permissions or the visible record
  (C2/R1); minor otherwise.
- **Why:** without `ORDER BY`, SQL returns rows in no guaranteed order, so the "first" row can
  change between runs.
- WRONG:
  ```js
  const sub = await prisma.subscription.findFirst({ where: { userId } });      // which of the user's subscriptions?
  ```
- CORRECT:
  ```js
  const sub = await prisma.subscription.findFirst({
    where: { userId, status: 'active' },
    orderBy: { startedAt: 'desc' },
  });
  ```
- **Fix:** add an `orderBy` that defines the intended row, or `findUnique` on a unique key.
- **Cite:** PostgreSQL docs, "Sorting Rows" (`ORDER BY`; without it the order is unspecified);
  Prisma docs, `findFirst`.
- **Tool code:** none.

## 13. Background jobs and queues

<!-- provenance: CodeWriter/node/refs/jobs-and-queues.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-COR-02` (a job that runs twice must be safe: idempotency key, processed-events
table), `NODE-COR-09` (singleton job without a distributed lock), `NODE-ERR-08` (a handler whose
rejection is unobserved), `NODE-ERR-10` (retry loop). Not flagged: queue library choice, separate
worker process, Bull Board, and DLQ alert thresholds.

### NODE-ERR-56 — Job added without attempts or backoff
- **Detect:** `queue.add(name, data)` with no `attempts` / `backoff` in the options or in the
  queue's `defaultJobOptions`, for a job that sends mail, charges, syncs or writes. BullMQ retries
  a failed job only when `attempts` is greater than 1.
- **Default severity:** major when the job moves money or data and a transient failure drops it
  (C2/R1); minor for best-effort work.
- **Why:** one network blip ends the job and nobody retries.
- WRONG:
  ```js
  await queue.add('send-receipt', { orderId });                 // one attempt only
  ```
- CORRECT:
  ```js
  await queue.add('send-receipt', { orderId }, {
    attempts: 5, backoff: { type: 'exponential', delay: 1000 }, jobId: `receipt:${orderId}`,
  });
  ```
- **Fix:** set `attempts` and exponential `backoff` (in `defaultJobOptions` for the whole queue)
  and make the handler idempotent.
- **Cite:** BullMQ docs, "Retrying failing jobs"; AWS Builders' Library, "Timeouts, retries and
  backoff with jitter".
- **Tool code:** none.

### NODE-COR-70 — Repeatable job registered on every start without a stable id
- **Detect:** `queue.add('nightly', {}, { repeat: { pattern: '0 3 * * *' } })` executed at
  application start-up with no `jobId` or `upsertJobScheduler`, so every restart and every replica
  adds another schedule.
- **Default severity:** major (C2/R1: the job runs N times per tick, with N growing at each deploy).
- **Why:** each registration creates a new repeatable entry.
- WRONG:
  ```js
  await queue.add('nightly-report', {}, { repeat: { pattern: '0 3 * * *' } });   // at boot, on every replica
  ```
- CORRECT:
  ```js
  await queue.upsertJobScheduler('nightly-report', { pattern: '0 3 * * *' }, { name: 'nightly-report' });
  ```
- **Fix:** an idempotent registration (`upsertJobScheduler`, or a stable `jobId`), done by one
  process.
- **Cite:** BullMQ docs, "Job Schedulers" and "Repeatable jobs".
- **Tool code:** none.

## 14. API design

<!-- provenance: CodeWriter/node/refs/api-design.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `NODE-ERR-05` (status codes, error shape), `NODE-PERF-05` (list endpoint with no cap:
a client-controlled `limit` must be clamped server-side), `NODE-PERF-07` (deep `OFFSET`). Not
flagged: URL naming, response envelopes, versioning scheme, OpenAPI generation, `Retry-After` and
`X-Request-Id` headers, unless they differ from sibling routes in the same diff.

### NODE-COR-71 — Breaking change to an existing public route
- **Detect:** the diff removes or renames a response field, changes a field's type or an enum's
  values, makes an optional request field required, changes a status code, or removes a route,
  on a route that is documented (OpenAPI, README, SDK) or consumed by another service, with no new
  version prefix and no deprecation period.
- **Default severity:** blocker for a documented public API with external consumers (a broken
  public contract); major for an internal API with known consumers. Question if the consumers are
  unknown.
- **Why:** existing clients break at the next deploy.
- WRONG:
  ```js
  // before: { id, name, price }   after:
  app.get('/products/:id', async (req) => ({ id: p.id, title: p.name, priceCents: p.price }));
  ```
- CORRECT:
  ```js
  app.get('/v2/products/:id', async (req) => ({ id: p.id, title: p.name, priceCents: p.price }));
  // /v1/products/:id keeps its shape; Deprecation and Sunset headers announce the end date
  ```
- **Fix:** add fields instead of changing them; version the route for a breaking change; announce
  deprecation.
- **Cite:** RFC 9745 (the `Deprecation` HTTP response header field); RFC 8594 (the `Sunset` header
  field); Google API Improvement Proposals AIP-180 (backwards compatibility).
- **Tool code:** none (an OpenAPI diff tool when the project has one).

## 15. DevOps and containers

<!-- provenance: CodeWriter/node/refs/devops-and-containers.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Applies to `Dockerfile`, compose files, Kubernetes manifests, CI workflows and start-up code in the
diff. The concepts are the same as in the Python checklist (`PY-OPS-01` to `PY-OPS-06`); the Node
forms follow. A secret in an image layer, `ENV`, `ARG` or `COPY .env` is `NODE-SEC-02` (blocker).
Absent controls are at most a question (X-SEV-09). Not flagged: multi-stage builds, image size,
`.dockerignore` contents, CI gate order.

### NODE-OPS-01 — Container runs as root
- **Detect:** the final stage has no `USER` instruction (the official `node` images run as root;
  they ship a `node` user to switch to); `runAsUser: 0`; `privileged: true`.
- **Default severity:** minor (C2/R2); major with `privileged: true` or a mounted Docker socket.
- **Why:** a compromise of the process is root in the container.
- WRONG:
  ```dockerfile
  FROM node:22-slim
  COPY . /app
  CMD ["node", "dist/server.js"]                 # root
  ```
- CORRECT:
  ```dockerfile
  FROM node:22-slim
  COPY --chown=node:node . /app
  USER node
  CMD ["node", "dist/server.js"]
  ```
- **Fix:** `USER node` before `CMD`.
- **Cite:** Docker docs, "Dockerfile best practices" (`USER`); OWASP Docker Security Cheat Sheet,
  Rule #2; Node.js Docker best practices (nodejs/docker-node).
- **Tool code:** none (`hadolint DL3002`).

### NODE-OPS-02 — Mutable base image or non-reproducible install
- **Detect:** `FROM node:latest` or an untagged image; `npm install` instead of `npm ci` in a
  Dockerfile or CI job; a missing lockfile copy; `curl ... | sh`.
- **Default severity:** minor (C3).
- **Why:** the build changes without a diff, and `npm install` may rewrite the lockfile.
- WRONG:
  ```dockerfile
  FROM node:latest
  COPY . .
  RUN npm install
  ```
- CORRECT:
  ```dockerfile
  FROM node:22.11-slim
  COPY package.json package-lock.json ./
  RUN npm ci --omit=dev
  ```
- **Fix:** pin the image tag or digest; `npm ci` with the lockfile.
- **Cite:** Docker docs, "Dockerfile best practices"; npm docs, `npm ci`.
- **Tool code:** none (`hadolint DL3007`).

### NODE-OPS-03 — Build leftovers in the runtime image
- **Detect:** one stage that holds `devDependencies`, TypeScript sources and the compiler in the
  image that runs; `COPY . .` before the `package*.json` copy (every code change reinstalls).
- **Default severity:** nit; minor when dev dependencies reach production.
- **Why:** a bigger attack surface and slower builds.
- WRONG:
  ```dockerfile
  COPY . .
  RUN npm ci && npm run build
  CMD ["node", "dist/server.js"]                  # image still holds src/ and devDependencies
  ```
- CORRECT:
  ```dockerfile
  FROM node:22-slim AS build
  COPY package*.json ./
  RUN npm ci
  COPY . .
  RUN npm run build
  FROM node:22-slim
  COPY package*.json ./
  RUN npm ci --omit=dev
  COPY --from=build /app/dist ./dist
  ```
- **Fix:** multi-stage build; copy manifests first.
- **Cite:** Docker docs, "Multi-stage builds" and "Dockerfile best practices".
- **Tool code:** none.

### NODE-OPS-04 — Health endpoint that lies
- **Detect:** a `/live` route that queries the database or an external API (an outage restarts
  every pod); a `/ready` route that returns 200 without checking required dependencies.
- **Default severity:** minor; major when liveness causes a restart storm during a dependency outage.
- **Why:** the orchestrator restarts on liveness and routes traffic on readiness.
- WRONG:
  ```js
  app.get('/live', async () => { await pool.query('SELECT 1'); return { ok: true }; });
  app.get('/ready', async () => ({ ok: true }));
  ```
- CORRECT:
  ```js
  app.get('/live', async () => ({ ok: true }));
  app.get('/ready', async (req, reply) => {
    try { await pool.query('SELECT 1'); return { ok: true }; }
    catch { return reply.code(503).send({ ok: false }); }
  });
  ```
- **Fix:** liveness checks the process; readiness checks required dependencies and returns 503.
- **Cite:** Kubernetes docs, "Configure Liveness, Readiness and Startup Probes".
- **Tool code:** none.

### NODE-OPS-05 — SIGTERM handler exits without draining
- **Detect:** `process.on('SIGTERM', () => process.exit(0))`, or no drain of in-flight requests,
  connections or queue jobs before exit.
- **Default severity:** minor; major for a worker holding jobs whose loss is a data loss.
- **Why:** the orchestrator sends SIGTERM, then SIGKILL after the grace period.
- WRONG:
  ```js
  process.on('SIGTERM', () => process.exit(0));             // cuts in-flight requests
  ```
- CORRECT:
  ```js
  process.on('SIGTERM', async () => {
    await app.close();                                        // Fastify: stops accepting, drains
    await pool.end();
    process.exit(0);
  });
  ```
- **Fix:** stop accepting connections, finish in-flight work, close pools, then exit.
- **Cite:** Kubernetes docs, "Pod Lifecycle" (termination); Fastify docs, `fastify.close()`.
- **Tool code:** none.

### NODE-OPS-06 — Unsafe schema change in the deploy path
- **Detect:** `prisma migrate dev` or `prisma db push` (or `--accept-data-loss`) in a Dockerfile,
  CI deploy job or start script; migrations run in the `CMD` of every replica; a drop-column
  migration in the same release as the code that stops using it; `synchronize: true` (TypeORM) in
  production.
- **Default severity:** major (C1/R2: data loss or a failed deploy).
- **Why:** `migrate dev` is for development (it can reset the database), `db push` skips migration
  history, and replicas race on the same migration.
- WRONG:
  ```dockerfile
  CMD npx prisma migrate dev && node dist/server.js
  ```
- CORRECT:
  ```yaml
  # CI/CD: one migration job before the rollout
  - run: npx prisma migrate deploy
  - run: kubectl rollout restart deployment/api
  ```
- **Fix:** `prisma migrate deploy` once per release before the new version starts; split destructive
  changes into a later release.
- **Cite:** Prisma docs, "Deploying database changes with Prisma Migrate" (`migrate deploy` in
  production, `migrate dev` in development) and "Prototyping with db push".
- **Tool code:** none.

### NODE-OPS-07 — Development log transport enabled in production
- **Detect:** `transport: { target: 'pino-pretty' }` set unconditionally, or without an
  `NODE_ENV`/config check, in code that ships.
- **Default severity:** minor (C3: slower logging and unparseable output for the log pipeline).
- **Why:** `pino-pretty` is a human formatter; log aggregators expect JSON.
- WRONG:
  ```js
  const logger = pino({ transport: { target: 'pino-pretty' } });
  ```
- CORRECT:
  ```js
  const logger = pino(process.env.LOG_PRETTY === '1' ? { transport: { target: 'pino-pretty' } } : {});
  ```
- **Fix:** pretty output only when explicitly enabled for local development.
- **Cite:** Pino docs, "Pretty Printing" (for development; use JSON in production).
- **Tool code:** none.
