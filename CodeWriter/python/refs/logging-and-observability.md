# Logging & Observability — Python Reference

Grounded in the **`logging`** stdlib docs, the **12-factor app** (logs as event streams), and the
**`logger_pkg`** package from `Dev_util_prj`. PII / secret rules cross-reference
`refs/api-and-secrets.md`.

## Use `logger_pkg` — not raw `logging` or `print`

`logger_pkg` from `Dev_util_prj` is a drop-in upgrade over stdlib `logging`: same
`get_logger(__name__)` API, but adds JSON/coloured output, PII scrubbing, non-blocking async
queue, and `contextvars`-based context propagation with no extra code.

**Install (clone from source):**

```bash
# GitHub URL
git clone https://github.com/damien220/Logger_Manager
pip install -e dist/logger_pkg-0.1.0-py3-none-any.whl
```

```python
# WRONG — print statements are invisible to log aggregators and can't be filtered
def process(order_id: str) -> None:
    print(f"Processing {order_id}")
    print("done")
```

```python
# CORRECT (logger_pkg — preferred)
from logger_pkg import setup_logging, get_logger, bound_context

# --- App entrypoint only (never in library code) ---
setup_logging(format="json", pii_filter_enabled=True)

# --- One logger per module; name = dotted module path ---
log = get_logger(__name__)

def process(order_id: str) -> None:
    log.info("Processing order", extra={"order_id": order_id})
    log.info("Order processed")
```

```python
# CORRECT (stdlib fallback — when logger_pkg is not available)
import logging

log = logging.getLogger(__name__)   # NOT logging.getLogger("myapp") — __name__ is portable

def process(order_id: str) -> None:
    log.info("Processing order", extra={"order_id": order_id})
```

The key difference: in `logger_pkg`, `setup_logging` is called once at the app entrypoint and
configures the whole hierarchy. Individual modules just call `get_logger(__name__)` — they never
configure handlers or formatters themselves.

## Context propagation with `bound_context`

Attach request-level context once per request and have it appear in every log record within that
scope — no threading or manual passing required.

```python
from logger_pkg import get_logger, bound_context

log = get_logger(__name__)

async def handle_request(request_id: str, user_id: str) -> None:
    with bound_context(request_id=request_id, user_id=user_id):
        log.info("Request started")           # {"request_id": "...", "user_id": "...", "msg": "..."}
        await do_work()
        log.info("Request finished")          # same context on every record inside the block
```

Stdlib equivalent using `contextvars` (no logger_pkg):

```python
import contextvars, logging

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True
```

## Log levels — choose deliberately

| Level      | Use for                                                                           |
| ---------- | --------------------------------------------------------------------------------- |
| `DEBUG`    | Developer diagnostics; disabled in production. Variable dumps, loop counts.       |
| `INFO`     | Normal operational events. Request received, job started/finished.                |
| `WARNING`  | Recoverable unexpected situations. Retry triggered, deprecated API used.          |
| `ERROR`    | A specific operation failed; the process continues. Caught exception, failed job. |
| `CRITICAL` | Process-level failure; app may not continue. DB unreachable at startup.           |

```python
# WRONG — wrong levels make filtering useless
log.info("Failed to connect to database")    # ERROR, not INFO
log.error("User logged in")                  # INFO, not ERROR
log.debug("Payment processed successfully")  # INFO, not DEBUG (lost in prod)
```

```python
# CORRECT
log.info("Payment processed", extra={"charge_id": charge.id, "amount": charge.amount})
log.warning("Retry attempt %d for charge %s", attempt, charge.id)
log.error("Payment gateway timeout", exc_info=True, extra={"charge_id": charge.id})
```

## Structured context — `extra={}` not f-strings

Log in machine-readable key-value pairs so aggregators (Loki, CloudWatch, Elasticsearch) can
query and alert on field values, not regex over message strings.

```python
# WRONG — context buried in the message string; not queryable
log.info(f"User {user_id} purchased {sku} for {amount} cents")
```

```python
# CORRECT — context as structured fields
log.info(
    "Purchase completed",
    extra={"user_id": user_id, "sku": sku, "amount_cents": amount},
)
```

With `logger_pkg` in `format="json"` mode these fields appear as top-level JSON keys in every
record. With stdlib, pass a formatter that emits them; the `extra` dict is still attached to the
`LogRecord` regardless of formatter.

## Secrets and PII must never reach logs

`logger_pkg` enables PII scrubbing (`pii_filter_enabled=True`) which strips emails, credit-card
numbers, SSNs, and token-shaped strings via regex. But that is a safety net — don't rely on it:
never put sensitive values into a message or `extra` intentionally.

```python
# WRONG — password and token in the log record
log.info("Auth attempt", extra={"password": password, "token": token})
log.error(f"Auth failed for token {token}")
```

```python
# CORRECT — log intent, not secrets
log.info("Auth attempt", extra={"user_id": user_id})
log.error("Auth failed (token redacted)")
```

See `refs/api-and-secrets.md` → "Secrets never reach logs or exceptions" for the full rule.

## `exc_info=True` for exceptions

Always capture the traceback when logging an exception so the root cause is preserved.

```python
try:
    result = call_gateway(charge)
except GatewayTimeout as err:
    log.error("Gateway timeout", exc_info=True, extra={"charge_id": charge.id})
    raise RetryableError("gateway timeout") from err
```

`exc_info=True` (or passing the exception directly in Python 3.11+) attaches the full traceback to
the log record. Without it, the message is useless for debugging.

## Library vs application config

| Rule                                                                                              | Reason                                                                                           |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Library code: `log = logging.getLogger(__name__)` only — no `basicConfig`, no `addHandler`        | Calling `basicConfig` in a library hijacks the root logger for every application that imports it |
| Application entrypoint: call `setup_logging(...)` (logger_pkg) or `logging.basicConfig(...)` once | Sets up the whole hierarchy; modules just get loggers                                            |

```python
# WRONG — library code configuring a handler
# mylib/client.py
import logging
logging.basicConfig(level=logging.DEBUG)   # poisons the caller's logging setup
log = logging.getLogger(__name__)
```

```python
# CORRECT — library
# mylib/client.py
import logging
log = logging.getLogger(__name__)           # nothing else; the app configures the root

# CORRECT — application entrypoint
# myapp/__main__.py
from logger_pkg import setup_logging
setup_logging(format="json", pii_filter_enabled=True)
```

## `logger_pkg` config via environment variables

`logger_pkg` reads `LOG_*` env vars at `setup_logging()` time — no code change between
environments:

```bash
LOG_LEVEL=DEBUG          # DEBUG / INFO / WARNING / ERROR / CRITICAL
LOG_FORMAT=json          # json (production) or console (development)
LOG_PII_FILTER=true      # strip PII patterns
LOG_FILE=app.log         # optional file sink alongside stdout
```

Add these to `.env.example` (never hardcode values in source).

---

## Health check endpoints — observability for orchestrators

Health endpoints let Kubernetes (and any orchestration layer) probe the service state. Keep them
simple and fast. See `refs/devops-and-deployment.md` for the full three-probe (`/live`, `/ready`,
`/startup`) implementation with K8s YAML. Key rule:

- `/live` — process is alive; no external checks (a failed DB must not kill the pod via liveness)
- `/ready` — all dependencies reachable; returns 503 when not ready (removes pod from LB)
- `/startup` — initialization complete (migrations, cache warm-up); disables liveness until done

---

## Prometheus metrics — `prometheus-client`

Expose standard process metrics and custom business/request counters at `GET /metrics`.
Prometheus scrapes this endpoint; Grafana visualizes it.

```bash
pip install prometheus-client
```

```python
# CORRECT — Prometheus setup in a FastAPI app
from prometheus_client import (
    Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, multiprocess, REGISTRY,
)
from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute
import time

# Counters and histograms — define once at module level (not per-request)
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code'],
)
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    buckets=[.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5],
)

app = FastAPI()

@app.middleware('http')
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)

    return response

@app.get('/metrics')
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

**Key rules:**

| Rule | Reason |
|---|---|
| Define metrics at module level (not in handlers) | Prometheus clients re-register on every call — raises `ValueError: duplicated timeseries` |
| Use `CONTENT_TYPE_LATEST` as the media type | Prometheus text format is not `text/plain`; wrong type causes scrape failures |
| Label cardinality: low and bounded | Never use user IDs or request IDs as label values — unbounded cardinality OOMs Prometheus |
| Multi-process mode (Gunicorn) | Set `PROMETHEUS_MULTIPROC_DIR` env var; use `multiprocess.MultiProcessCollector` |

```python
# Multi-process Prometheus (Gunicorn — each worker has its own registry)
import os
from prometheus_client import CollectorRegistry, multiprocess, generate_latest

def get_metrics_response() -> bytes:
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return generate_latest(registry)
```

---

## OpenTelemetry — distributed tracing for Python services

OpenTelemetry correlates traces across services. When service A calls service B, the `traceparent`
header carries the trace ID so both appear in one waterfall view.

```bash
pip install opentelemetry-sdk opentelemetry-instrumentation-fastapi \
            opentelemetry-instrumentation-httpx opentelemetry-instrumentation-sqlalchemy \
            opentelemetry-exporter-otlp
```

```python
# CORRECT — tracing.py must be imported BEFORE FastAPI and other instrumented libs
# tracing.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

def setup_tracing(service_name: str, otlp_endpoint: str) -> None:
    provider = TracerProvider()
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument()
```

```python
# main.py — import tracing FIRST
import tracing                            # must precede FastAPI and httpx imports
from fastapi import FastAPI
from settings import settings

tracing.setup_tracing(
    service_name='my-api',
    otlp_endpoint=settings.otlp_endpoint,  # e.g. 'http://jaeger:4317'
)

app = FastAPI()
```

```python
# Manual span — annotate business logic that is worth tracing individually
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def process_payment(charge_id: str, amount_cents: int) -> dict:
    with tracer.start_as_current_span('process_payment') as span:
        span.set_attribute('charge.id', charge_id)
        span.set_attribute('charge.amount_cents', amount_cents)
        result = await gateway.charge(charge_id, amount_cents)
        span.set_attribute('charge.status', result['status'])
        return result
```

**Key rules:**

| Rule | Reason |
|---|---|
| `tracing.py` imported before all other libs | Auto-instrumentation patches at import time; late import misses some spans |
| W3C `traceparent` header on all outbound calls | `HTTPXClientInstrumentor` injects this automatically; use it for stdlib `urllib` too |
| Manual spans for business logic, not framework calls | Auto-instrumentation already covers HTTP/DB/cache; add manual spans only where you need custom attributes |
| `BatchSpanProcessor` in production | `SimpleSpanProcessor` blocks the request thread on every export — production always uses batched async export |
