---
name: node-web-best-style
description: Use when writing, editing, refactoring, or reviewing Node.js or TypeScript web
  code to produce idiomatic, performant, and secure web services. Enforces ESM modules, strict
  TypeScript, proper async patterns, Fastify/Express/Hono best practices, Zod input validation,
  Helmet security headers, RFC 9457 error responses, Pino structured logging, and safe secret
  management. Triggers on .js/.ts/.mjs/.mts files, "write a Node API", "refactor this route",
  "write a Fastify handler", "make this idiomatic TypeScript", or "best practice".
---

# Node.js Web Best Style

## Identity & Mission

You write Node.js and TypeScript web code that is *idiomatic, performant, and secure* — not
merely code that runs. Resolve style from the named authoritative source (Airbnb style guide,
OWASP, Fastify docs, RFC 9457, Pino docs, …) and apply the pattern that fits the task, stating
the rationale (readability / performance / safety) when it is non-obvious.

**Language baseline:** TypeScript 5.5+ on Node.js 22 LTS. ESM only (`"type": "module"`).
`tsx` for development; `tsc`/`esbuild` for production builds.

**Idiom is per-language:** Node.js uses `camelCase` for variables/functions, `PascalCase`
for classes/types, and `UPPER_SNAKE_CASE` for constants. Never import another language's
conventions.

**How to use this skill.** The titles below are the always-loaded summary — each is an
authoritative rule you can apply directly. Do **not** pre-load the `refs/`. When the current
task matches a title's `Read … when:` trigger, load that one ref for deep guidance (WRONG vs
CORRECT examples, comparison tables, citations), then apply it. Before declaring code done,
run the pre-ship gate (final title).

---

## Titles

### 1. Naming & modules
Use `camelCase` for variables/functions, `PascalCase` for classes/interfaces/types, and
`UPPER_SNAKE_CASE` for module-level constants. File names are `kebab-case.ts`. Use ESM
everywhere (`import`/`export`, `"type": "module"` in `package.json`) — `require()` is legacy.
Specify file extensions explicitly in imports (`.js`). Prefer named exports over default.
Read **`refs/naming-and-modules.md`** when: naming anything, choosing ESM vs CJS, ordering
imports, deciding on file names, or adding `module.exports`.

### 2. TypeScript & types
Always `"strict": true`; always `"verbatimModuleSyntax": true`. Use `import type` for
type-only imports. Use `unknown` at all external boundaries (catch clauses, JSON.parse,
external API responses) — never `any`. All public functions have explicit return type
annotations. Derive types with utility types (`Partial<T>`, `Omit<T, K>`) rather than
re-declaring. Use `satisfies` over `as` type assertions; prefer `const enum` or `as const`
objects over numeric `enum`.
Read **`refs/typescript-and-types.md`** when: writing type annotations, setting up tsconfig,
choosing `interface` vs `type`, working with generics, resolving a `strict` mode error, or
picking an enum pattern.

### 3. Web frameworks
Use **Fastify** for new APIs (2–3× faster than Express, built-in validation, TypeScript-native,
plugin encapsulation). Express for legacy codebases. Hono for edge/serverless. All routes must
have schema or Zod validation on body, params, and query — never use `req.body` directly. Every
server must register graceful shutdown (`SIGTERM`/`SIGINT` → `server.close()`). Use
`AsyncLocalStorage` for per-request context, never module-level globals.
Read **`refs/web-frameworks.md`** when: writing a route handler, designing middleware, choosing
a framework, setting up a plugin, wiring lifecycle hooks, or adding graceful shutdown.

### 4. Security
Apply `helmet()` as the first middleware/plugin — it sets 14+ HTTP security headers. Configure
CORS with an explicit origin allowlist from env, never `origin: '*'` in production. Validate
every external input with Zod `safeParse()` (not `parse()` in handlers). Use parameterized
queries only — never string-interpolate SQL. Rate-limit all public endpoints; tighten on auth
routes. Store JWT refresh tokens in `HttpOnly` + `SameSite=Strict` cookies, not localStorage.
Read **`refs/security-web.md`** when: adding authentication, configuring CORS, writing input
validation, constructing DB queries, adding rate limiting, handling file uploads, or reviewing
code for security issues.

### 5. Error handling
All HTTP error responses must follow RFC 9457 Problem Details (`type`, `title`, `status`,
`detail`, `instance`; `Content-Type: application/problem+json`). Route handlers throw typed
`AppError` subclasses; a single centralized error handler (`fastify.setErrorHandler` or Express
4-arg middleware) formats and logs them. Never include a stack trace in the HTTP response. Use
`catch (err: unknown)` and narrow with `instanceof`. Register `process.on('unhandledRejection')`
with `process.exit(1)`.
Read **`refs/error-handling-web.md`** when: writing try/catch, designing the error middleware,
defining custom error classes, propagating async errors, or deciding what goes in the response
vs the logs.

### 6. Async patterns
Use `async/await` everywhere — no `.then()` chains in new code. Every Promise must be awaited
or `.catch()`-handled; a floating promise is a crash waiting to happen (ESLint
`no-floating-promises` enforces this). Use `Promise.allSettled` when partial failure is
acceptable; `Promise.any` for fallback races. Use `AbortController` for cancellable operations.
Pipe large data as streams (`stream/promises.pipeline`), never buffer into memory. Cap
concurrent Promises with `p-limit` when iterating large arrays.
Read **`refs/async-patterns.md`** when: writing concurrent code, choosing a Promise combinator,
adding cancellation, streaming large data, working with event emitters, or diagnosing a
floating-promise warning.

### 7. Logging & observability
Use **Pino** — never `console.log` in production code. Create one shared logger; use child
loggers to propagate per-request context (`requestId`, `userId`). Always log structured objects
first: `logger.info({ userId, action }, 'message')` — never string interpolation. Secrets, PII,
and tokens must never appear in log payloads; configure `pino.redact` for known paths. Use raw
JSON output in production (no `pino-pretty`). Library code emits no logs.
Read **`refs/logging-observability.md`** when: adding log calls, setting up the Pino logger,
propagating request context, reviewing code for secrets-in-logs, or integrating with a log
aggregator.

### 8. Config & secrets
Never hardcode API keys, passwords, tokens, or connection strings — read from `process.env`
via a validated `env` object. Validate all environment variables at startup with Zod; fail fast
with a clear message if any are missing or malformed. Keep secrets in `.env` (gitignored); commit
`.env.example` with keys and dummy values. Export a single `env` object — no scattered
`process.env.FOO` calls in application code. Use explicit feature flags for behavior differences,
not `NODE_ENV`.
Read **`refs/config-and-secrets.md`** when: reading env vars, setting up config validation,
handling credentials, writing deployment config, or reviewing code for hardcoded secrets.

### 9. Testing
Use **Vitest** for new projects (native ESM, 10–20× faster watch mode, Jest-compatible API).
Test HTTP routes with `fastify.inject()` or Supertest — no real server port. Structure tests as
`describe` > `describe` > `it()`; keep each `it()` to one observable behavior in AAA shape.
Mock at system boundaries only (DB client, HTTP client, external SDKs) — never mock internal
functions. Reset mocks in `beforeEach`. Target 80%+ coverage on business logic and route
handlers.
Read **`refs/testing-web.md`** when: writing tests, setting up Vitest config, mocking a
dependency, testing error paths, or deciding what to assert.

### 10. Performance
The event loop is the request processor — any synchronous work > 1 ms on the main thread is
latency for all concurrent requests. Move CPU-bound work to `node:worker_threads` (or `piscina`
for pools). Never use `*Sync` APIs in request handlers. Stream large payloads — never buffer.
Define Fastify route response schemas (TypeBox) to use the fast-json-stringify serializer.
Always use a DB connection pool. Set server `keepAliveTimeout` > the load balancer idle timeout.
Profile with `clinic.js` before optimizing.
Read **`refs/performance-web.md`** when: a handler is slow, processing large data, choosing
between sync and async variants, scaling for concurrency, configuring keep-alive, or setting up
PM2 clustering.

### 11. Database & ORM
Use **Prisma** (schema-first, excellent DX, first-class migrations) for most projects; **Drizzle**
for serverless/edge or SQL-control-critical workloads. Always wrap multi-step mutations in a
transaction (`$transaction` / `db.transaction()`). Always use `select` on every ORM query — never
fetch entire rows. Prevent N+1 queries with `include`/eager loading. Run `prisma migrate deploy`
as the first step of every production deployment; never modify applied migrations.
Read **`refs/database-and-orm.md`** when: choosing an ORM, writing DB queries, adding a
transaction, handling migrations, configuring the connection pool, or implementing soft deletes.

### 12. Background jobs & queues
Use **BullMQ** (Redis-backed) for all work that must not block the HTTP request cycle — email,
file processing, webhooks, scheduled tasks. Every job must declare `attempts` + exponential
`backoff`. Every job that mutates state must be **idempotent** (safe to run twice). Run workers
in a **separate process** from the HTTP server. Monitor the DLQ (failed jobs set) and alert on
growth. Use `redlock` for singleton jobs that must not run concurrently.
Read **`refs/jobs-and-queues.md`** when: adding async tasks, choosing a queue library, setting
retry policies, preventing duplicate job execution, scheduling cron jobs, or wiring up Bull Board.

### 13. API design
URLs identify resources; HTTP verbs carry the action. Return **bare resources** for single objects;
**`{ items, nextCursor, hasMore }`** for paginated lists. Use **cursor pagination** (not offset) for
all production list endpoints. Version breaking changes with `/api/v2/` URL prefix; signal
deprecation with `Deprecation` + `Sunset` headers. Auto-generate **OpenAPI 3.1** docs from Fastify
TypeBox schemas via `@fastify/swagger`. Use semantic HTTP status codes — never `200` with an error body.
Read **`refs/api-design.md`** when: designing URL structure, choosing pagination strategy, setting up
Swagger docs, picking HTTP status codes, adding API versioning, or designing response envelopes.

### 14. DevOps & containers
Use **multi-stage Dockerfiles**: compile in `node:22-slim`, run in `node:22-alpine` copying only
`dist/` and prod `node_modules`. Always run as a non-root user. Include a `.dockerignore`. Expose
three health endpoints: `GET /live` (liveness — process alive), `GET /ready` (readiness — deps
reachable), `GET /startup` (initialization complete) — configured as Kubernetes probes. Register
`SIGTERM` shutdown handler that drains in-flight requests before exiting. Run `prisma migrate deploy`
before the new server version starts in CI/CD.
Read **`refs/devops-and-containers.md`** when: writing a Dockerfile, setting up Docker Compose,
adding health check endpoints, configuring Kubernetes probes, wiring graceful shutdown, or designing
a CI/CD deploy pipeline.

### Pre-ship gate
Before calling Node.js/TypeScript web code done, validate it against
**`tooling/style-checklist.md`** and ensure these three commands pass from the project root:

```bash
npx eslint .               # naming, floating-promises, no-any, import/order, security rules
npx tsc --noEmit           # strict type checking, verbatimModuleSyntax, noUncheckedIndexedAccess
npx prettier --check .     # formatting
```

The checklist is the verifiable counterpart to the rules above — a failing item is a fix, not
a suggestion. Copy `tooling/eslint.config.js`, `tooling/prettier.config.js`, and
`tooling/tsconfig.base.json` into the target project as the starting configuration.
