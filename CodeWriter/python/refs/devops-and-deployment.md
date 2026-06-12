# DevOps & Deployment — Python Reference

Grounded in **Docker multi-stage build best practices**, **PEP 517/518 build system docs**,
**Kubernetes health check docs**, **Gunicorn/Uvicorn process model docs**, and the
**12-factor app** deployment principles. A well-containerized Python service is reproducible,
minimal, and responds correctly to orchestration lifecycle events.

---

## Dockerfile — multi-stage build for Python

A single-stage Dockerfile installs dev dependencies, build tooling, and leaves build artifacts
(`.pyc`, `__pycache__`, uv/pip cache) in the final image. Multi-stage separates build-time from
runtime, producing a minimal image.

```dockerfile
# WRONG — single stage: ships build tooling, dev deps, source + virtualenv in one layer
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "myapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
# CORRECT — multi-stage: builder installs deps; runtime copies only what is needed

# ── Stage 1: build ─────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder
WORKDIR /app

# Install build system; keep in builder only
RUN pip install --no-cache-dir uv

# Copy manifests first — cached unless pyproject.toml / uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY src/ ./src/

# ── Stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime
WORKDIR /app

# Only copy installed packages and application source from builder
COPY --from=builder /usr/local/lib /usr/local/lib
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/src ./src

# Security: run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/live')" \
  || exit 1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "myapp.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--no-access-log"]
```

**Key rules:**
- `python:3.13-slim` base (~50 MB vs ~900 MB for `python:3.13`); avoid Alpine for Python unless you need the absolute minimum — C extensions (cryptography, psycopg2) require build tools on Alpine and can silently fall back to pure-Python slower variants
- `PYTHONUNBUFFERED=1` — ensures stdout/stderr reach the log aggregator immediately (no buffering)
- `PYTHONDONTWRITEBYTECODE=1` — no `.pyc` files in the runtime image; reduce layer size
- `pip install --no-cache-dir` / `uv pip install --no-cache` — avoids embedding pip cache in the layer
- `USER appuser` — never run Python as root inside a container
- Layer order: manifests + install before source copy — Docker caches the install layer until deps change

---

## `.dockerignore` — prevent context bloat

Without `.dockerignore`, `COPY . .` sends your entire working directory to the Docker daemon —
including `.venv` (potentially GB-sized), `__pycache__`, `.git`, test files, and `.env`.

```dockerignore
# .dockerignore
.venv
__pycache__
*.pyc
*.pyo
*.pyd
.git
.gitignore
*.md
.env
.env.*
.coverage
.pytest_cache
htmlcov
dist
build
*.egg-info
tests
docs
.mypy_cache
.ruff_cache
docker-compose*.yml
Dockerfile*
```

---

## Docker Compose — local development environment

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports: ['8000:8000']
    environment:
      ENV: development
      DATABASE_URL: postgresql+asyncpg://postgres:password@db:5432/myapp
      REDIS_URL: redis://cache:6379/0
    volumes:
      - ./src:/app/src       # hot-reload: mount source in dev
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    command: uvicorn myapp.main:app --reload --host 0.0.0.0 --port 8000

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
      POSTGRES_DB: myapp
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports: ['5432:5432']
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U postgres']
      interval: 5s
      timeout: 5s
      retries: 5

  cache:
    image: redis:7-alpine
    ports: ['6379:6379']
    healthcheck:
      test: ['CMD', 'redis-cli', 'ping']
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  postgres_data:
```

---

## Health check endpoints — three distinct signals

Same three-probe model applies to Python web apps (FastAPI shown; adapt for Flask/Django).

| Endpoint | Signal | Kubernetes probe | Action on failure |
|---|---|---|---|
| `GET /live` | Process is alive | `livenessProbe` | **Restart the pod** |
| `GET /ready` | Ready to serve traffic | `readinessProbe` | **Remove from load balancer** (no restart) |
| `GET /startup` | Initialization complete | `startupProbe` | Prevents liveness/readiness until ready |

```python
# CORRECT — FastAPI health check endpoints
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

_app_initialized = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _app_initialized
    # Startup: run migrations, warm caches, init pools
    await database.connect()
    _app_initialized = True
    yield
    # Shutdown: close connections
    await database.disconnect()

app = FastAPI(lifespan=lifespan)

@app.get('/live')
async def liveness() -> JSONResponse:
    # Only checks the process is running; no external dep checks
    return JSONResponse({'status': 'ok'})

@app.get('/ready')
async def readiness() -> JSONResponse:
    errors: list[str] = []
    try:
        await database.execute('SELECT 1')
    except Exception as exc:
        errors.append(f'db: {exc}')
    try:
        await redis_client.ping()
    except Exception as exc:
        errors.append(f'redis: {exc}')

    if errors:
        return JSONResponse({'status': 'not ready', 'errors': errors},
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return JSONResponse({'status': 'ready'})

@app.get('/startup')
async def startup_check() -> JSONResponse:
    if not _app_initialized:
        return JSONResponse({'status': 'starting'},
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return JSONResponse({'status': 'started'})
```

```yaml
# Kubernetes deployment spec
livenessProbe:
  httpGet:
    path: /live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 15
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 2

startupProbe:
  httpGet:
    path: /startup
    port: 8000
  failureThreshold: 30    # allow 30 × 2s = 60s for startup
  periodSeconds: 2
```

---

## Graceful shutdown — drain in-flight requests

Uvicorn and Gunicorn handle `SIGTERM` by default (drain then exit). For custom shutdown logic,
use FastAPI lifespan (shown above) or signal handlers for other frameworks.

```python
# Gunicorn with custom signal handling (standalone script)
import signal
import sys

def handle_sigterm(signum: int, frame: object) -> None:
    print('SIGTERM received — shutting down gracefully')
    # Cleanup: close DB pools, flush log buffers, complete in-flight jobs
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
```

```bash
# Gunicorn production command (4 worker processes, async workers with uvicorn worker class)
gunicorn myapp.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 30 \
  --graceful-timeout 30 \
  --access-logfile -
```

**Rule:** `--graceful-timeout` must be ≤ Kubernetes `terminationGracePeriodSeconds`. Workers that
exceed the graceful timeout are hard-killed, dropping in-flight requests.

---

## CI/CD pipeline for Python

Gate order ensures fast feedback; type + lint errors surface before the slower test and security scans.

```yaml
# .github/workflows/deploy.yml (conceptual)
jobs:
  ci:
    steps:
      - name: Install
        run: uv pip install -e ".[dev]"

      - name: Lint
        run: ruff check . && ruff format --check .

      - name: Type check
        run: mypy src/

      - name: Tests
        run: pytest --cov=src --cov-report=xml

      - name: Security audit
        run: pip-audit --vulnerability-service pypi --fail-on-cvss 7

      - name: Build Docker image
        run: docker build -t $IMAGE_TAG .

      - name: Run DB migrations
        run: alembic upgrade head
        # Runs BEFORE the new server version starts — migrations must be backward-compatible

      - name: Deploy
        run: # platform-specific deploy command
```

**Migration safety rule:** Alembic migrations deployed to production must be
**backward-compatible** with the *previous* application version (additive schema changes only).
Deploy the migration first, then the new application code — enables zero-downtime rolling updates.

---

## Environment variable injection — never bake secrets into images

```bash
# Docker run (local/staging)
docker run -e DATABASE_URL="$DATABASE_URL" -e STRIPE_KEY="$STRIPE_KEY" my-api

# Fly.io
flyctl secrets set DATABASE_URL="postgresql://..." STRIPE_KEY="sk_live_..."

# Kubernetes Secret
kubectl create secret generic api-secrets \
  --from-literal=DATABASE_URL="postgresql://..." \
  --from-literal=STRIPE_KEY="sk_live_..."
```

```yaml
# Kubernetes deployment — inject secret as env vars
containers:
  - name: api
    image: myregistry/api:1.2.3
    envFrom:
      - secretRef:
          name: api-secrets
```

**Rule:** Docker images contain zero secrets. The same image runs in staging and production with
different env vars. A leaked image is not a secret leak.
