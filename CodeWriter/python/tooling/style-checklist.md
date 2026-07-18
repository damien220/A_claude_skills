# Style Checklist — Python Pre-Ship Gate

The skill runs this final pass before declaring Python code done. Each item maps to a ref;
if an item fails, fix it and re-check. This is the verifiable counterpart to the prose rules —
most items are also enforced by `ruff.toml` / `mypy.ini`, noted as `[ruff: CODE]` / `[mypy]`.

## Naming & layout → `refs/naming-and-layout.md`
- [ ] `snake_case` for variables/functions, `PascalCase` for classes, `UPPER_CASE` for constants `[ruff: N]`
- [ ] No single-letter names except short-lived loop/index vars; names say what they hold
- [ ] Imports grouped stdlib → third-party → first-party, alphabetized `[ruff: I]`
- [ ] Module/file names are short, lowercase, `snake_case`; no `utils.py` dumping ground
- [ ] No cross-module import of a leading-`_` name; promote it to the module's public API instead

## Typing & contracts → `refs/typing-and-contracts.md`
- [ ] Every function has parameter + return type hints `[mypy: disallow_untyped_defs]`
- [ ] `X | None` (not bare `X` with a `None` default); no implicit Optional `[mypy]`
- [ ] Modern syntax: `list[int]`, `X | Y` over `List[int]`, `Union[...]` `[ruff: UP]`
- [ ] No `Any` leaking out of a public signature `[mypy: warn_return_any]`

## Data modeling → `refs/classes-and-data-modeling.md`
- [ ] A class earns its keep (has state + behavior); else a function or `@dataclass` is used
- [ ] `@dataclass(frozen=True, slots=True)` for value objects where immutability fits
- [ ] No mutable default arguments (`def f(x=[])`) `[ruff: B006]`

## Abstraction → `refs/abstraction-interfaces-polymorphism.md`
- [ ] `Protocol` for duck-typed interfaces; `ABC` only when sharing implementation
- [ ] Composition over deep inheritance; no `isinstance` ladders where dispatch fits

## Sync vs async → `refs/sync-async-concurrency.md`
- [ ] `async` used only for I/O-bound work; CPU-bound uses threads/`multiprocessing`
- [ ] No blocking calls (`time.sleep`, sync `requests`, blocking file I/O) inside a coroutine
- [ ] Concurrent awaits use `asyncio.gather` / `TaskGroup`, not a serial await loop

## Performance → `refs/performance-efficiency.md`
- [ ] Comprehensions/generators over manual `append` loops `[ruff: C4, PERF]`
- [ ] `set`/`dict` membership for hot lookups; no O(n) `in list` in a loop
- [ ] Builtins/stdlib over hand-rolled equivalents; `functools.cache` where repeat calls justify it
- [ ] Profiled with `cProfile` or `py-spy` before any optimization; hot path identified from data
- [ ] Distributed caching (Redis) used in multi-worker deployments; no process-local `functools.cache` shared-state assumption
- [ ] Cache keys include a version component; on mutation, version counter incremented (not individual key delete)
- [ ] No cache stampede: distributed lock (`redis.set(key, nx=True, ex=ttl)`) used before DB refetch under miss

## Error handling → `refs/error-handling.md`
- [ ] Specific exception types; no bare `except:` `[ruff: E722]`
- [ ] `raise NewError(...) from err` preserves the cause chain
- [ ] No silent `except: pass`; cleanup uses context managers, not `finally` juggling
- [ ] A resource that outlives one `with` block (cache, singleton) has both `close()` and a
  `weakref.finalize` safety net
- [ ] A silent automatic fallback (catch-and-degrade) emits `warnings.warn`, not just a log line
- [ ] `ruff check` is clean — this is what catches an undefined-name typo hiding in an untested
  `except` branch, not manual testing of every error path

## APIs & secrets → `refs/api-and-secrets.md`
- [ ] No hardcoded keys/tokens/passwords — read from env/secret manager `[ruff: S105–S107]`
- [ ] `.env` is gitignored, dev-only, and loaded once via an explicit `cwd`-relative path (no
  parent-directory walk); only `.env.example` is committed
- [ ] All env vars validated at startup via `pydantic-settings` `BaseSettings`; process exits if any are missing
- [ ] Secret values wrapped in `pydantic.SecretStr` (or equivalent) so they cannot be printed accidentally
- [ ] Every outbound network call sets a timeout; retries use backoff; remote (non-local) endpoints
  are required/warned to use TLS, not plaintext HTTP
- [ ] Parameterized queries only — no string-formatted SQL `[ruff: S608]`
- [ ] Untrusted content (external text, another module's stored data) is sanitized before it's
  interpolated into a prompt template, `str.format()` call, or other structured text sink
- [ ] A file path sourced from a DB or config is resolved and checked against its intended root
  before opening (path traversal); stored paths are relative to a known root, not absolute
- [ ] Secrets never appear in logs or exception messages; inputs are validated
- [ ] `pip-audit --fail-on-cvss 7` passes in CI (no high/critical dependency CVEs)

## Packaging & structure → `refs/packaging-and-structure.md`
- [ ] Heavy optional SDKs (LLM/cloud clients) are imported inside the function/branch that uses
  them, not at module top level — unrelated commands don't pay their import cost
- [ ] No hand-copied helper duplicated across modules — a second call site imports the shared one
- [ ] No module has drifted past ~500–700 lines or one function per unrelated concern without a split

## Docs & tests → `refs/docs-and-comments.md`, `refs/testing.md`
- [ ] Public functions/classes have docstrings (PEP 257); comments explain *why*, not *what*
- [ ] Tests follow Arrange-Act-Assert; boundaries mocked, not internals

## Logging → `refs/logging-and-observability.md`
- [ ] `get_logger(__name__)` per module; zero `print()` calls for diagnostic output
- [ ] Log level chosen deliberately (DEBUG/INFO/WARNING/ERROR/CRITICAL) — not all `info`
- [ ] Library code has `logging.getLogger(__name__)` only — no `basicConfig`, no `addHandler`
- [ ] Structured context in `extra={}`, not concatenated into the message string
- [ ] No secrets, tokens, passwords, or PII in log messages or `extra` values
- [ ] Exceptions logged with `exc_info=True` to capture the full traceback
- [ ] If `logger_pkg` is available: `setup_logging(pii_filter_enabled=True)` at app entrypoint

## Observability — web services → `refs/logging-and-observability.md`
- [ ] `GET /metrics` endpoint exposes Prometheus metrics (`prometheus-client`); `collectDefaultMetrics` enabled
- [ ] Custom `http_requests_total` Counter and `http_request_duration_seconds` Histogram recorded per route + status code
- [ ] Prometheus label cardinality is low and bounded — no user IDs or request IDs used as label values
- [ ] OpenTelemetry SDK initialized in `tracing.py` imported before FastAPI/httpx/SQLAlchemy when distributed tracing is needed
- [ ] W3C `traceparent` header propagated on all outbound service-to-service HTTP calls

## DevOps & deployment → `refs/devops-and-deployment.md`
- [ ] Dockerfile uses multi-stage build: builder installs deps; runtime copies only `src/` + installed packages
- [ ] Container runs as non-root user; `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1` set
- [ ] `.dockerignore` excludes `.venv`, `__pycache__`, `.git`, `.env`, test files, build artifacts
- [ ] `GET /live` returns 200 (process alive — no external dep checks)
- [ ] `GET /ready` returns 503 if DB or cache unreachable; 200 when all dependencies are healthy
- [ ] `SIGTERM` handled gracefully (Uvicorn/Gunicorn drain by default; custom handler for non-web services)
- [ ] Alembic migrations run **before** new server version starts in CI/CD pipeline
- [ ] CI pipeline gates in order: `ruff` → `mypy` → `pytest` → `pip-audit` → Docker build → migrate → deploy
- [ ] Secrets injected at runtime by platform; no secrets baked into Docker image

## Dev_util_prj packages
- [ ] Infrastructure concerns (logging, caching, DB, errors, HTTP clients, events, scheduling)
  use the appropriate `Dev_util_prj` package rather than a hand-rolled implementation.
  Wheels: `/workspaces/Prj_utils/Dev_util_prj/Dependencies/`

## Final
- [ ] `ruff check` clean; `ruff format` applied; `mypy` clean
