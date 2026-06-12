# DevOps & Containers — Node.js Reference

Grounded in **Docker multi-stage build best practices**, **Kubernetes health check docs**,
**NodeShift Node.js Reference Architecture**, and **OneUptime health check guide 2026**.
A well-containerized Node.js app is reproducible, minimal, and responds correctly to
Kubernetes lifecycle events.

---

## Dockerfile — multi-stage build

A single-stage Dockerfile copies `node_modules` including dev dependencies, TypeScript source,
and build tooling into the final image. Multi-stage builds compile in a heavy builder and copy
only the necessary output into a minimal runtime image.

```dockerfile
# WRONG — single stage: ships devDependencies, source files, and build tools (~800 MB)
FROM node:22
WORKDIR /app
COPY package*.json .
RUN npm install
COPY . .
RUN npm run build
CMD ["node", "dist/server.js"]
```

```dockerfile
# CORRECT — multi-stage: builder compiles; runtime ships only dist + prod deps (~150 MB)

# ── Stage 1: build ─────────────────────────────────────────────────────────────
FROM node:22-slim AS builder
WORKDIR /app

# Copy manifests first — cached unless package*.json changes (faster rebuilds)
COPY package*.json ./
RUN npm ci                        # exact lockfile versions; faster and deterministic

COPY tsconfig*.json ./
COPY src/ ./src/
RUN npm run build                  # produces dist/

# ── Stage 2: runtime ───────────────────────────────────────────────────────────
FROM node:22-alpine AS runtime
WORKDIR /app

# Install only production dependencies in the final image
COPY package*.json ./
RUN npm ci --only=production && npm cache clean --force

COPY --from=builder /app/dist ./dist

# Security: run as non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

# Expose port; document it (does not publish)
EXPOSE 3000

# Health check baked into the image
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "const h=require('http');h.get('http://localhost:3000/live',(r)=>{process.exit(r.statusCode===200?0:1)}).on('error',()=>process.exit(1))"

ENV NODE_ENV=production
CMD ["node", "dist/server.js"]
```

**Key rules:**
- `node:22-alpine` runtime (base image ~50 MB vs ~900 MB for `node:22`); use `node:22-slim` for builder if Alpine toolchain causes issues
- `npm ci` not `npm install` — exact lockfile install, fails if lockfile is out of sync
- `--only=production` in runtime stage eliminates dev dependencies
- `npm cache clean --force` after install to reduce layer size
- `USER appuser` — never run Node.js as `root` in a container
- Layer order: `package*.json` copy + `npm ci` before source copy — Docker caches the install layer until packages change

---

## `.dockerignore` — prevent context bloat

Without `.dockerignore`, `COPY . .` sends your entire working directory to the Docker daemon
including `node_modules` (often GB-sized), `.env`, `.git`, and test files.

```dockerignore
# .dockerignore
node_modules
dist
.git
.gitignore
*.md
.env
.env.*
coverage
.nyc_output
**/*.test.ts
**/*.spec.ts
.vscode
.idea
docker-compose*.yml
Dockerfile*
```

---

## Docker Compose — local development environment

Encode your local service dependencies in `docker-compose.yml` so any developer can start the
full stack with `docker compose up -d`.

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports: ['3000:3000']
    environment:
      NODE_ENV: development
      DATABASE_URL: postgres://postgres:password@db:5432/myapp
      REDIS_URL: redis://cache:6379
    volumes:
      - ./src:/app/src    # hot-reload: mount source, not dist
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    command: npx tsx watch src/server.ts   # dev: tsx watch for hot reload

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

Kubernetes (and any orchestration platform) needs to distinguish between three states. Conflating
them causes unnecessary pod restarts or keeps broken pods in rotation.

| Endpoint | Signal | Kubernetes probe | Action on failure |
|---|---|---|---|
| `GET /live` | Process is alive | `livenessProbe` | **Restart the pod** |
| `GET /ready` | Ready to accept traffic | `readinessProbe` | **Remove from load balancer** (no restart) |
| `GET /startup` | Initialization complete | `startupProbe` | Prevents liveness/readiness checks until app is initialized |

```ts
// CORRECT — three endpoints with appropriate checks
// /live: only checks that the process is running; no external dependencies
// Returning 503 here tells Kubernetes to kill and restart the pod
fastify.get('/live', async (_request, reply) => {
  return reply.status(200).send({ status: 'ok' });
});

// /ready: checks that all dependencies are reachable
// Returning 503 removes this pod from the load balancer rotation (no traffic)
fastify.get('/ready', async (_request, reply) => {
  const checks = await Promise.allSettled([
    prisma.$queryRaw`SELECT 1`,     // DB reachable?
    redis.ping(),                    // Cache reachable?
  ]);

  const failed = checks.filter((r) => r.status === 'rejected');
  if (failed.length > 0) {
    const errors = failed.map((r) => (r as PromiseRejectedResult).reason?.message);
    return reply.status(503).send({ status: 'not ready', errors });
  }

  return reply.status(200).send({ status: 'ready' });
});

// /startup: called during initialization; disables liveness/readiness until this passes
// Use when startup involves DB migrations or long initialization
fastify.get('/startup', async (_request, reply) => {
  if (!appInitialized) {
    return reply.status(503).send({ status: 'starting' });
  }
  return reply.status(200).send({ status: 'started' });
});
```

```yaml
# Kubernetes deployment spec
livenessProbe:
  httpGet:
    path: /live
    port: 3000
  initialDelaySeconds: 10
  periodSeconds: 15
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 3000
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 2

startupProbe:
  httpGet:
    path: /startup
    port: 3000
  failureThreshold: 30     # allow 30 × 2s = 60s for startup
  periodSeconds: 2
```

---

## Non-root user — never run as root in containers

Running Node.js as `root` inside a container means that if the process is compromised, the
attacker has root access to the container filesystem and potentially to host volumes.

```dockerfile
# WRONG — default Node.js image runs as root
FROM node:22-alpine
COPY dist/ ./dist/
CMD ["node", "dist/server.js"]
# ps inside: root  1  node dist/server.js
```

```dockerfile
# CORRECT — create and switch to non-root user
FROM node:22-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
# Ensure the user owns the working directory
RUN chown -R appuser:appgroup /app

USER appuser
CMD ["node", "dist/server.js"]
```

Alternatively, `node:22-alpine` ships with a `node` user (uid 1000) — use `USER node` directly.

---

## Environment variable injection at runtime

Never bake secrets into Docker images. Pass secrets as environment variables at runtime via
your orchestration platform.

```bash
# Docker run (local/staging)
docker run -e DATABASE_URL="$DATABASE_URL" -e STRIPE_KEY="$STRIPE_KEY" my-api

# Fly.io
flyctl secrets set DATABASE_URL="postgres://..." STRIPE_KEY="sk_live_..."

# Kubernetes — Secret mounted as env vars
kubectl create secret generic api-secrets \
  --from-literal=DATABASE_URL="postgres://..." \
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
different env vars. A leaked Docker image is not a secret leak.

---

## Graceful shutdown — drain in-flight requests

Kubernetes sends `SIGTERM` before killing a pod. The application has `terminationGracePeriodSeconds`
(default 30s) to finish in-flight work before receiving `SIGKILL`.

```ts
// CORRECT — Fastify graceful shutdown on SIGTERM
let isShuttingDown = false;

const shutdown = async (signal: string): Promise<void> => {
  if (isShuttingDown) return;
  isShuttingDown = true;

  logger.info({ signal }, 'Received shutdown signal; draining requests');

  // Stop accepting new requests; wait for in-flight to complete
  await fastify.close();

  // Close downstream connections
  await prisma.$disconnect();
  await redis.quit();
  await emailQueue.close();

  logger.info('Shutdown complete');
  process.exit(0);
};

process.on('SIGTERM', () => void shutdown('SIGTERM'));
process.on('SIGINT',  () => void shutdown('SIGINT'));
```

```yaml
# Kubernetes: give the app time to drain before hard kill
spec:
  terminationGracePeriodSeconds: 30
```

---

## CI/CD pipeline essentials

A production deployment pipeline must pass these gates in order:

```yaml
# .github/workflows/deploy.yml (conceptual)
jobs:
  ci:
    steps:
      - name: Install
        run: npm ci

      - name: Type check
        run: npx tsc --noEmit

      - name: Lint
        run: npx eslint .

      - name: Test
        run: npx vitest run --coverage

      - name: Security audit
        run: npm audit --audit-level=high

      - name: Build Docker image
        run: docker build -t $IMAGE_TAG .

      - name: Run DB migrations
        run: npx prisma migrate deploy
        # Runs BEFORE the new server version starts — migrations must be backward-compatible

      - name: Deploy
        run: # platform-specific deploy command
```

**Migration safety rule:** Migrations deployed to production must be **backward-compatible**
with the *previous* version of the application. Deploy the migration first, then the new app code.
This enables zero-downtime rolling updates and safe rollbacks.
