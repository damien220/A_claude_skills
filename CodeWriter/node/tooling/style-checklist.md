# Node.js Web Style Checklist

This is the pre-ship gate. Before declaring any Node.js/TypeScript web code done, validate every
section that applies to the change. A failing item is a fix, not a suggestion.

Run `npx eslint . && npx tsc --noEmit && npx prettier --check .` before opening a PR.

---

## Naming & Modules → `refs/naming-and-modules.md`

- [ ] `camelCase` for variables and functions; `PascalCase` for classes, interfaces, and types
- [ ] `UPPER_SNAKE_CASE` for module-level constants (`MAX_RETRIES`, `DEFAULT_TIMEOUT_MS`)
- [ ] File names are `kebab-case.ts` (modules) or `PascalCase.ts` (single-class files)
- [ ] No `require()` in new code; `import`/`export` everywhere; `"type": "module"` in `package.json`
- [ ] File extensions explicit in ESM imports (`./user-service.js`, not `./user-service`)
- [ ] `import type` used for type-only imports (`@typescript-eslint/consistent-type-imports` passes)
- [ ] Import order: `node:` built-ins → third-party → first-party; separated by blank lines
- [ ] Named exports preferred over default exports (except framework entry points)
- [ ] Private class state uses `#field` (ES2022), not `_field` convention

---

## TypeScript → `refs/typescript-and-types.md`

- [ ] `"strict": true` in tsconfig; no sub-flag disabled without a comment explaining why
- [ ] `"verbatimModuleSyntax": true`; type-only imports use `import type`
- [ ] No `any` in non-test code; `unknown` used at external boundaries (catch, JSON.parse, API responses)
- [ ] All public functions have explicit return type annotations
- [ ] `unknown` narrowed in `catch` blocks with `instanceof` before accessing properties
- [ ] No `as` type assertions unless absolutely necessary; prefer `satisfies` or type guards
- [ ] Utility types used for derivations (`Partial<T>`, `Omit<T, K>`, etc.) — no manual re-declaration
- [ ] Enums use string values (`const enum` or `as const` object); no bare numeric `enum`
- [ ] `tsc --noEmit` passes with zero errors

---

## Web Framework → `refs/web-frameworks.md`

- [ ] All route handlers have schema/Zod validation on body, params, and query — never use raw `req.body`
- [ ] Fastify: every domain feature is a plugin (`fastify.register()`); no ad hoc root-scope decoration
- [ ] Express: async routes wrapped in `asyncHandler()`; no raw async route without rejection handling
- [ ] Graceful shutdown registered: `SIGTERM`/`SIGINT` → `fastify.close()` / `server.close()`
- [ ] No module-level mutable globals used to store per-request state; use `AsyncLocalStorage` or `req`
- [ ] Middleware order documented in Express setups; security headers come first

---

## Security → `refs/security-web.md`

- [ ] `helmet()` (or `@fastify/helmet`) registered as the first plugin/middleware
- [ ] CORS origin is an allowlist from env var — no `origin: '*'` in production
- [ ] Every route validates all inputs (body, params, query, headers) with Zod `safeParse()` or TypeBox
- [ ] No string-interpolated SQL; parameterized queries / ORM used exclusively
- [ ] `npm audit --audit-level=high` passes (no high/critical vulnerabilities)
- [ ] Rate limiting applied to all public endpoints; stricter limits on auth endpoints
- [ ] Auth tokens: short-lived access JWTs; refresh tokens in `HttpOnly` + `SameSite=Strict` cookies
- [ ] No `eval`, no `new Function()`, no `child_process.exec` with user-supplied input
- [ ] SSRF prevention: outbound URLs from user input validated against allowlist or blocked IP ranges

---

## Error Handling → `refs/error-handling-web.md`

- [ ] All HTTP error responses follow RFC 9457 (`type`, `title`, `status`, `detail`, `instance`)
- [ ] `Content-Type: application/problem+json` on all error responses
- [ ] Stack traces never serialized into HTTP response bodies
- [ ] Single centralized error handler: `fastify.setErrorHandler()` or Express 4-arg middleware
- [ ] 5xx responses return a generic safe message; real cause logged server-side
- [ ] `catch (err: unknown)` used; narrowed with `instanceof` before accessing `.message` or other fields
- [ ] `process.on('unhandledRejection', ...)` and `process.on('uncaughtException', ...)` registered with `process.exit(1)`
- [ ] `AppError` (or equivalent typed error hierarchy) used for domain errors; `throw new Error()` only for truly unexpected cases

---

## Async Patterns → `refs/async-patterns.md`

- [ ] No `.then()` chains in new code; `async/await` everywhere
- [ ] No floating promises; `@typescript-eslint/no-floating-promises` passes
- [ ] `Promise.allSettled` used when partial failure is acceptable; results checked for `status === 'rejected'`
- [ ] `AbortController` used for cancellable operations (outbound fetch, long DB queries, stream operations)
- [ ] No `*Sync` APIs (`readFileSync`, `writeFileSync`, etc.) inside request handlers
- [ ] `stream/promises.pipeline` used for large data pipelines (not `pipe()` with manual error handling)
- [ ] Unbounded `Promise.all` over large arrays replaced with a concurrency-limited alternative (`p-limit`)

---

## Logging → `refs/logging-observability.md`

- [ ] No `console.log` / `console.error` in production code; Pino used throughout
- [ ] Log calls use object bindings first: `logger.info({ userId, action }, 'message')` — no string interpolation
- [ ] Request ID (`requestId`) propagated through all log lines within a request (via child logger or `AsyncLocalStorage`)
- [ ] No secrets, tokens, passwords, or PII in log payloads; `pino.redact` configured for known paths
- [ ] `pino-pretty` transport only in non-production environments; raw JSON in production
- [ ] Library code emits no logs; accepts optional `logger` parameter with `noopLogger` default
- [ ] Log levels used correctly: `debug` for dev-only data; `info` for normal ops; `warn` for recoverable; `error` for failures; `fatal` + `process.exit(1)` for unrecoverable

---

## Config & Secrets → `refs/config-and-secrets.md`

- [ ] No hardcoded secrets, API keys, tokens, or passwords anywhere in source
- [ ] `.env` is in `.gitignore`; `.env.example` is committed with all required keys
- [ ] All environment variables validated at startup with Zod; startup exits with clear error if validation fails
- [ ] Single `env` exported object; no `process.env.FOO` scattered through application code
- [ ] Secrets wrapped in `Secret` type (or equivalent) to prevent accidental logging/serialization
- [ ] `NODE_ENV` not used for security decisions; explicit feature flags used instead

---

## Testing → `refs/testing-web.md`

- [ ] HTTP integration tests use `fastify.inject()` or Supertest — no real HTTP port allocated
- [ ] Tests follow Arrange-Act-Assert structure; each `it()` tests one observable behavior
- [ ] Mocks applied only at system boundaries (DB client, HTTP client, external SDKs) — never internal functions
- [ ] `vi.clearAllMocks()` called in `beforeEach` (or `clearMocks: true` in vitest config)
- [ ] Async tests use `async/await`; no `done` callback
- [ ] Vitest coverage thresholds set for branches, functions, and lines on business logic

---

## Performance → `refs/performance-web.md`

- [ ] No `*Sync` API calls (`readFileSync`, `pbkdf2Sync`, etc.) anywhere in request path
- [ ] CPU-bound work > 1 ms delegated to worker threads (`node:worker_threads` or `piscina`)
- [ ] Large file/data responses streamed, not buffered in memory
- [ ] Fastify response schemas defined to use `fast-json-stringify` serializer (not `JSON.stringify`)
- [ ] Database connections use a pool with explicit size; no per-request `new Connection()`
- [ ] Server `keepAliveTimeout` set; greater than the load balancer's idle connection timeout

---

## Database & ORM → `refs/database-and-orm.md`

- [ ] ORM chosen deliberately: Prisma (DX/migrations) or Drizzle (serverless/SQL-control); TypeORM not used for new projects
- [ ] Every `findMany()` / `select()` has an explicit `select` or column list — no bare `SELECT *` fetches
- [ ] All multi-step DB mutations wrapped in a transaction (`$transaction` or `db.transaction()`)
- [ ] No N+1 queries: related data loaded with `include`/join in the same query, not in a loop
- [ ] `prisma migrate deploy` (or equivalent) runs as the first step of every production deployment
- [ ] Connection pool configured with deliberate `max` size; idle + connection timeouts set
- [ ] Soft-delete pattern used where data must not be permanently destroyed; `deletedAt: null` filter applied globally

---

## Background Jobs & Queues → `refs/jobs-and-queues.md`

- [ ] All async work that must survive a process crash uses BullMQ (or equivalent Redis-backed queue)
- [ ] Every job declares `attempts` (≥ 3) and exponential `backoff`
- [ ] All state-mutating jobs are idempotent: safe to execute twice with identical outcome
- [ ] Workers run in a **separate process** from the HTTP server
- [ ] Failed jobs (DLQ) monitored; alert threshold set on backlog size
- [ ] Cron/repeatable jobs registered idempotently at startup (check before adding)
- [ ] Worker process registers `SIGTERM`/`SIGINT` → `worker.close()` for graceful shutdown
- [ ] Singleton jobs (must-not-run-concurrently) use distributed lock (`redlock`)

---

## API Design → `refs/api-design.md`

- [ ] URLs use nouns for resources; HTTP verbs carry the action (no `/getUser` etc.)
- [ ] Single objects: bare resource response (no `{ data: {...} }` envelope)
- [ ] List endpoints: `{ items, nextCursor, hasMore }` shape; cursor pagination for > 1000 rows
- [ ] Max page size enforced server-side (e.g. `limit: max(100)`)
- [ ] Semantic HTTP status codes used correctly (201 for create, 204 for delete, 409 for conflict, etc.)
- [ ] Breaking changes versioned under `/api/v2/` URL prefix; old version deprecated with `Deprecation` + `Sunset` headers
- [ ] OpenAPI 3.1 spec generated from TypeBox/Zod schemas via `@fastify/swagger`; available at `/api/docs/json`
- [ ] Rate limit responses include `Retry-After` and `X-RateLimit-*` headers
- [ ] `X-Request-Id` echoed in every response header

---

## DevOps & Containers → `refs/devops-and-containers.md`

- [ ] Dockerfile uses multi-stage build: builder (`node:22-slim`) + runtime (`node:22-alpine`)
- [ ] Runtime stage copies only `dist/` and production `node_modules`; no source files, no dev deps
- [ ] Container runs as non-root user (`USER node` or custom `appuser`)
- [ ] `.dockerignore` excludes `node_modules`, `.env`, `.git`, `dist`, test files
- [ ] `GET /live` returns 200 (process alive check only — no external deps)
- [ ] `GET /ready` returns 503 if DB or cache unreachable; 200 when dependencies are healthy
- [ ] `SIGTERM` handler registered: drains in-flight requests → closes DB/cache connections → `process.exit(0)`
- [ ] `terminationGracePeriodSeconds` in Kubernetes spec ≥ server keepAliveTimeout
- [ ] DB migrations run **before** new server version starts in CI/CD pipeline
- [ ] CI pipeline gates: `tsc --noEmit` → `eslint` → `vitest run` → `npm audit --audit-level=high` → build → migrate → deploy

---

## Observability Extensions → `refs/logging-observability.md`

- [ ] `GET /metrics` endpoint exposes Prometheus metrics (prom-client `collectDefaultMetrics` + custom counters)
- [ ] `http_requests_total` and `http_request_duration_seconds` histograms recorded per route + status code
- [ ] OpenTelemetry SDK initialized before all other imports when distributed tracing is needed
- [ ] W3C `traceparent` header propagated on all outbound service-to-service HTTP calls
