---
name: python-best-style
description: Use when writing, editing, refactoring, or reviewing Python code to produce
  idiomatic, performant, and secure Python. Enforces PEP 8 / PEP 484 naming and typing,
  proper data modeling (dataclasses, Protocol/ABC), correct sync vs async choices, efficient
  algorithms/idioms, robust error handling, and safe API/secret handling. Triggers on .py
  files, "write/refactor/review Python", "make this Pythonic", or "best practice".
---

# Python Best Style

## Identity & Mission

You write Python that is *idiomatic, performant, and secure* — not merely code that runs. Resolve
style from the named authoritative source (PEP 8/257/484/544/557/…, OWASP, the stdlib docs) and
apply the pattern that fits the task, stating the rationale (readability / performance / safety)
when it is non-obvious. Idiom is **per-language**: Python uses `snake_case` / `PascalCase` /
`UPPER_CASE` — never carry another language's conventions in.

**How to use this skill.** The titles below are the always-loaded summary — each is an
authoritative rule you can apply directly. Do **not** pre-load the `refs/`. When the current task
matches a title's `Read … when:` trigger, load that one ref for the deep guidance (WRONG vs
CORRECT examples, comparison tables, citations), then apply it. Before declaring code done, run
the pre-ship gate (final title).

**Dev_util_prj packages — use before reimplementing.** Before writing infrastructure from scratch
(logging, caching, DB access, error handling, HTTP clients, event dispatching, job scheduling,
notifications, plugin systems, workflow orchestration, agent scaffolding, or UI controllers),
check whether a `Dev_util_prj` package already covers it. Read the README at
`/workspaces/Prj_utils/Dev_util_prj/README.md` for the full package list and quick-start
examples; pre-built wheels for offline install are in
`/workspaces/Prj_utils/Dev_util_prj/Dependencies/`. The packages share common abstractions
(`BaseAppException`, `AbstractDatabase`, `AbstractCache`, …) and compose cleanly — use them
instead of reimplementing. Key packages by concern:

| Concern | Package | Import |
|---|---|---|
| Logging / observability | `Logger_Package` | `logger_pkg` |
| Error handling | `Error-Exception_Handler` | `error_handler` |
| Caching | `Cache_manager` | `cache_manager` |
| Database CRUD | `DB_Package` | `db_accessor` |
| Config scaffolding | `Config_Manager` | `config_manager_factory` |
| HTTP API client base | `API_Base_cl` | `api_client_base` |
| Plugin lifecycle | `Plugin_Loader` | `plugin_loader` |
| Event bus | `Event_Dispatcher` | `event_dispatcher` |
| Notifications | `Notification_manager` | `notification_manager` |
| Background jobs | `Job_Manager` | `job_manager` |
| Multi-step workflows | `Workflow_manager` | `workflow_manager` |
| LLM agent base | `Abstract_agent` | `abstract_agent` |
| Tool adapter | `Tool_Interface_adapter` | `tool_interface_adapter` |
| Shared Pydantic models | `InOut_Models` | `inout_models` |
| UI controller | `UI_controlBase` | `ui_controller_base` |

## Titles

### 1. Naming & module layout
Use `snake_case` for variables/functions, `PascalCase` for classes, `UPPER_CASE` for constants;
a leading `_` marks non-public API. Names describe what a thing *is*, not its type; modules are
short and lowercase, with imports ordered stdlib → third-party → first-party.
Read **`refs/naming-and-layout.md`** when: naming anything, ordering imports, choosing a module
or file name, or deciding what a name should reveal.

### 2. Data modeling: classes, dataclasses, structs
A class must earn its keep — prefer a function when there is no state, a `@dataclass`
(`frozen`/`slots`) for value objects, and reach for `NamedTuple` / `TypedDict` / Pydantic only
when their specific tradeoff fits. Never use a mutable default argument. For Enums, pick the
right subclass (`StrEnum`, `IntEnum`, `Flag`) for the values you need.
Read **`refs/classes-and-data-modeling.md`** when: defining a class, modeling a record/struct,
choosing among dataclass/NamedTuple/TypedDict/Pydantic/Enum, or optimizing instance memory.

### 3. Abstraction, interfaces & polymorphism
Prefer `typing.Protocol` for structural ("duck-typed") interfaces and `abc.ABC` only when you
need shared implementation or runtime enforcement. Favor composition over deep inheritance;
replace `isinstance` ladders with polymorphic methods, `singledispatch`, or `match`/`case`
(Python 3.10+).
Read **`refs/abstraction-interfaces-polymorphism.md`** when: defining an interface, choosing
ABC vs Protocol, designing a class hierarchy, or replacing type-dispatch branching.

### 4. Type hints & contracts
Fully annotate every public function (parameters and return); use modern syntax — `list[int]`,
`X | None`, `Literal`, `Final` — and let types serve as the contract mypy verifies. Reach for
`TypeVar`/generics for reusable containers, not for one-off code. Match syntax to the project's
minimum Python version.
Read **`refs/typing-and-contracts.md`** when: adding/auditing type hints, writing generics,
choosing `Optional`/`Union`/`Literal`/`Final`, resolving a mypy error, or checking which syntax
requires which Python version.

### 5. Sync vs async & concurrency
Choose async only for I/O-bound concurrency; use threads for blocking I/O you can't make async
and `multiprocessing` for CPU-bound work. Never call a blocking function inside a coroutine, and
gather concurrent awaits with `asyncio.gather`/`TaskGroup` instead of awaiting them serially.
Read **`refs/sync-async-concurrency.md`** when: deciding sync vs async, writing coroutines,
parallelizing I/O or CPU work, or diagnosing an event loop that stalls.

### 6. Performance & efficiency
Reach for builtins, the stdlib, and comprehensions/generators before hand-rolled loops; pick the
data structure that makes the hot operation O(1) (`set`/`dict` membership). Measure before
optimizing, and cache repeat work with `functools.cache` where it pays.
Read **`refs/performance-efficiency.md`** when: a loop is hot, choosing a data structure,
processing large/streamed data, or a profile points at an obvious inefficiency.

### 7. Error handling & exceptions
Catch the *specific* exception, never a bare `except:`; chain with `raise NewError(...) from err`
to preserve the cause, and never silently swallow errors. Prefer EAFP (`try`) over LBYL guards,
and use context managers for cleanup. For structured error responses (HTTP status codes, machine-
readable codes), prefer `error_handler` from `Dev_util_prj`.
Read **`refs/error-handling.md`** when: writing `try`/`except`, defining custom exceptions,
managing resources/cleanup, or deciding whether to catch, re-raise, or let an error propagate.

### 8. APIs, I/O & secret management
Never hardcode keys, tokens, or passwords — read them from environment variables or a secret
manager, with `.env` gitignored. Every outbound call sets a timeout and retries with backoff;
inputs are validated, and secrets never reach logs or exception messages. For building HTTP API
clients, prefer `api_client_base` from `Dev_util_prj` (retries, auth, circuit breaker included).
Read **`refs/api-and-secrets.md`** when: calling an external API, handling credentials/config,
making HTTP/network/file requests, or reviewing code for leaked secrets.

### 9. Testing
Write pytest tests in Arrange-Act-Assert shape; use fixtures for setup, `parametrize` for input
matrices, and mock only at system boundaries — never internal logic. Coverage targets behavior,
not lines.
Read **`refs/testing.md`** when: adding or restructuring tests, designing fixtures, mocking a
dependency, or deciding what a test should actually assert.

### 10. Documentation & comments
Write docstrings (Google/NumPy style, PEP 257) for public functions, classes, and modules; let
comments explain *why*, not *what*, and let type hints carry the "what". Keep docs next to code so
they stay true.
Read **`refs/docs-and-comments.md`** when: writing docstrings, commenting non-obvious logic,
documenting a public API, or a comment merely restates the code.

### 11. Packaging & project structure
Use a `src/` layout with a single `pyproject.toml` declaring metadata, dependencies, and entry
points (PEP 517/518/621). Pin or constrain dependencies deliberately and expose console scripts
through entry points rather than loose scripts.
Read **`refs/packaging-and-structure.md`** when: starting a project, adding a dependency or CLI
entry point, configuring `pyproject.toml`, or organizing modules into a package.

### 12. Logging & observability
Use one `get_logger(__name__)` call per module — never `print()` for diagnostic output. Choose
log levels deliberately (DEBUG/INFO/WARNING/ERROR/CRITICAL) and emit structured context as
key-value pairs so aggregators can query it. Secrets, PII, and tokens must never appear in log
messages. **Prefer `logger_pkg` from `Dev_util_prj`** over raw stdlib `logging` — it adds PII
scrubbing, JSON/coloured output, and `contextvars`-based context propagation with zero extra code.
For web services: expose `GET /metrics` (Prometheus `prometheus-client`) and initialize
OpenTelemetry before all other imports (`tracing.py` first).
Read **`refs/logging-and-observability.md`** when: adding log calls, setting up logging config,
emitting structured context, reviewing code for secrets-in-logs, integrating `logger_pkg`,
setting up Prometheus metrics, or adding distributed tracing with OpenTelemetry.

### 13. DevOps & deployment
Use **multi-stage Dockerfiles**: `python:3.13-slim` builder (installs deps) → `python:3.13-slim`
runtime (copies only installed packages and `src/`). Always run as a non-root user. Set
`PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`. For web services, expose three health
endpoints: `GET /live` (liveness — process alive), `GET /ready` (readiness — deps reachable),
`GET /startup` (initialization complete) — configured as Kubernetes probes. Gate CI/CD in order:
`ruff` → `mypy` → `pytest` → `pip-audit` → Docker build → `alembic upgrade head` → deploy.
Read **`refs/devops-and-deployment.md`** when: writing a Dockerfile, setting up Docker Compose,
adding health check endpoints, configuring Kubernetes probes, wiring graceful shutdown, designing
a CI/CD pipeline, or auditing dependencies for vulnerabilities.

### Pre-ship gate
Before calling Python code done, validate it against **`tooling/style-checklist.md`** and ensure
`ruff check` (config `tooling/ruff.toml`), `ruff format`, and `mypy` (config `tooling/mypy.ini`)
all pass. The checklist is the verifiable counterpart to the rules above — a failing item is a
fix, not a suggestion.
