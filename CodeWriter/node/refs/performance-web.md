# Performance — Node.js Web Reference

Grounded in the **Node.js "Don't Block the Event Loop" guide**, **`node:worker_threads` docs**,
**Node.js Streams docs**, **PM2 docs**, and **clinic.js**. The central invariant: the event loop
is the request processor. Every synchronous millisecond on the main thread is latency for all
concurrent requests.

---

## The event loop rule — no blocking on the main thread

Node.js handles concurrent requests with a single event loop thread. A synchronous operation
that takes 100 ms blocks *all* in-flight requests for 100 ms. Operations that take > 1 ms and
do not involve I/O must move to worker threads.

```ts
// WRONG — crypto.pbkdf2Sync blocks the event loop for ~200ms; 500 rps × 200ms = all requests stalled
app.post('/auth/login', async (req, res) => {
  const hash = crypto.pbkdf2Sync(req.body.password, user.salt, 100_000, 64, 'sha512');
  // ... verify hash
});
```

```ts
// CORRECT — use the async version; libuv threads handle the work off-main-thread
app.post('/auth/login', async (req, res) => {
  const hash = await crypto.pbkdf2(req.body.password, user.salt, 100_000, 64, 'sha512');
  // crypto.pbkdf2 is already async and uses the threadpool — no worker thread needed here
});
```

---

## Worker threads — CPU-bound work

Move genuinely CPU-intensive work to `node:worker_threads`. The main thread stays free to
handle I/O while the worker runs on a separate V8 isolate.

Use worker threads for:
- Password hashing (bcrypt `bcrypt.hash()` is already async via threadpool, but argon2 CPU work)
- Image processing (`sharp` uses libuv but heavy transforms still matter)
- Large JSON transformations (> 10 ms)
- ML inference
- Any CPU-bound loop

```ts
// WRONG — large data transformation on the main thread; event loop blocked for duration
app.post('/reports', async (req, res) => {
  const report = transformLargeDataset(req.body.records);  // could take seconds
  res.json(report);
});
```

```ts
// CORRECT — delegate to a worker thread
// workers/report-worker.ts
import { parentPort, workerData } from 'node:worker_threads';
const result = transformLargeDataset(workerData.records);
parentPort?.postMessage(result);

// route handler
import { Worker } from 'node:worker_threads';
import { fileURLToPath } from 'node:url';

function runReportWorker(records: Record[]): Promise<Report> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(
      new URL('./workers/report-worker.js', import.meta.url),
      { workerData: { records } }
    );
    worker.once('message', resolve);
    worker.once('error', reject);
    worker.once('exit', (code) => {
      if (code !== 0) reject(new Error(`Worker exited with code ${code}`));
    });
  });
}

fastify.post('/reports', async (request, reply) => {
  const report = await runReportWorker(request.body.records);
  return reply.send(report);
});
```

For a production use case, maintain a worker pool (e.g. `workerpool` or `piscina`) to avoid
the overhead of spawning a new worker per request.

---

## Never use `*Sync` APIs in request handlers

Every `*Sync` function in `fs`, `crypto`, and `dns` blocks the event loop for its entire
duration. They are acceptable only in startup scripts and CLI tools.

```ts
// WRONG — all synchronous; block event loop in request handlers
fs.readFileSync('./template.html');
crypto.randomBytes(32);  // the sync version
dns.lookupSync(hostname);
```

```ts
// CORRECT — async equivalents; libuv handles I/O on the thread pool
const template = await fs.promises.readFile('./template.html', 'utf8');
const randomBytes = await promisify(crypto.randomBytes)(32);
// Or: crypto.getRandomValues() is synchronous but non-blocking (uses OS CSPRNG directly)
```

---

## Streams for large payloads

Buffering a multi-MB response into a single `Buffer` or string before sending:
1. blocks the event loop while accumulating
2. peaks memory at `payload_size × concurrent_requests`
3. delays the first byte until the entire payload is ready

Stream it instead: the client starts receiving bytes immediately and memory stays O(chunk size).

```ts
// WRONG — entire file in RAM; memory spikes with concurrent downloads
fastify.get('/export', async (_request, reply) => {
  const data = await fs.promises.readFile('./exports/users.csv');   // potentially 500 MB
  return reply.send(data);
});
```

```ts
// CORRECT — stream: first byte sent immediately; memory O(chunk size)
import { createReadStream } from 'node:fs';
import { pipeline } from 'node:stream/promises';

fastify.get('/export', async (_request, reply) => {
  const stream = createReadStream('./exports/users.csv');
  reply.header('Content-Type', 'text/csv');
  reply.header('Content-Disposition', 'attachment; filename="users.csv"');
  return reply.send(stream);
});

// DB cursor → stream for large query results
fastify.get('/users/export', async (_request, reply) => {
  const cursor = db.query('SELECT * FROM users').cursor();   // pg cursor
  reply.header('Content-Type', 'application/json');
  // transform cursor → JSON array stream without buffering all rows
  return reply.send(buildJsonArrayStream(cursor));
});
```

---

## JSON serialization — Fastify's fast-json-stringify

`JSON.stringify` is a general-purpose serializer that handles every edge case. Fastify compiles
a dedicated serialization function from the route's `response` JSON Schema at startup time —
4–6× faster for the common case.

```ts
// WRONG — bypasses the compiled serializer; hits the generic JSON.stringify path
reply.header('Content-Type', 'application/json').send(JSON.stringify(user));
```

```ts
// CORRECT — define response schema; Fastify auto-compiles a serializer
import { Type } from '@sinclair/typebox';

const UserResponseSchema = Type.Object({
  id:        Type.String(),
  email:     Type.String(),
  name:      Type.String(),
  createdAt: Type.String({ format: 'date-time' }),
});

fastify.get('/users/:id', {
  schema: {
    response: { 200: UserResponseSchema },  // compiled once at startup
  },
}, async (request) => {
  return userService.getById(request.params.id);  // Fastify serializes automatically
});
```

The schema also strips extra fields from the response — a security benefit that prevents
accidentally leaking internal fields (e.g. `passwordHash`).

---

## Connection pooling — always

Database connections are expensive (TCP handshake, auth, server-side state). Opening a new
connection per request adds 10–100 ms of latency and exhausts server connection limits under load.

```ts
// WRONG — new connection per request
fastify.get('/users', async (request) => {
  const client = await postgres.connect();   // new connection every time
  const users = await client.query('SELECT * FROM users');
  await client.end();
  return users.rows;
});
```

```ts
// CORRECT — shared pool; connections reused across requests
import { Pool } from 'pg';

const pool = new Pool({
  connectionString: env.DATABASE_URL,
  max: Math.max(4, Math.floor(os.cpus().length * 2)),  // 2× CPU count, minimum 4
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 5_000,
});

// Register on Fastify; pool closed gracefully on shutdown
fastify.decorate('db', pool);
fastify.addHook('onClose', async () => { await pool.end(); });

fastify.get('/users', async (request) => {
  const { rows } = await request.server.db.query('SELECT * FROM users');
  return rows;
});
```

---

## HTTP keep-alive

HTTP keep-alive reuses TCP connections across requests. Node.js 13+ enables it by default.
Ensure your `keepAliveTimeout` is longer than your load balancer's idle timeout — otherwise
the LB closes connections while Node thinks they're still open, causing 502 errors.

```ts
// CORRECT — explicit keepAlive configuration
const server = fastify.server;   // underlying http.Server

// Default is 5s in Node.js; set higher than the LB idle timeout (commonly 60–120s)
server.keepAliveTimeout = 65_000;       // 65 seconds
server.headersTimeout = 66_000;         // must be > keepAliveTimeout
```

---

## Process clustering with PM2

A single Node.js process uses one CPU core. On an 8-core machine, a single process uses ~12%
of available compute. PM2 cluster mode spawns one process per core and load-balances connections.

```bash
# Install globally or as a dev dependency
npm install -g pm2

# Start in cluster mode — one process per CPU core
pm2 start dist/server.js --name api -i max

# Zero-downtime reload (restart workers one by one; no dropped connections)
pm2 reload api

# ecosystem.config.js — commit this for reproducible deployment
```

```js
// ecosystem.config.cjs
module.exports = {
  apps: [{
    name: 'api',
    script: './dist/server.js',
    instances: 'max',      // one per CPU core
    exec_mode: 'cluster',
    max_memory_restart: '512M',
    env_production: {
      NODE_ENV: 'production',
      LOG_LEVEL: 'info',
    },
  }],
};
```

For containerized environments (Kubernetes, Fly.io), run one process per container and use the
orchestrator's horizontal pod autoscaling instead of PM2 clustering.

---

## Caching — layer by layer

| Layer | Tool | TTL | Use for |
|---|---|---|---|
| In-process | `lru-cache` | Short (< 1 min) | Parsed config, expensive computation, small reference data |
| Shared / distributed | Redis via `ioredis` | Minutes to hours | DB query results, session data, rate limit counters |
| HTTP cache headers | `Cache-Control`, `ETag` | Browser/CDN decides | GET endpoints returning stable data |

```ts
// CORRECT — LRU cache for expensive but rarely-changing data
import { LRUCache } from 'lru-cache';

const featureFlagCache = new LRUCache<string, FeatureFlags>({
  max: 500,
  ttl: 60_000,          // 1 minute
});

async function getFeatureFlags(tenantId: string): Promise<FeatureFlags> {
  const cached = featureFlagCache.get(tenantId);
  if (cached) return cached;

  const flags = await db.getFeatureFlags(tenantId);
  featureFlagCache.set(tenantId, flags);
  return flags;
}
```

```ts
// CORRECT — ETag for HTTP caching on read-heavy endpoints
fastify.get('/config', async (_request, reply) => {
  const config = await loadPublicConfig();
  const etag = crypto.createHash('sha256')
    .update(JSON.stringify(config))
    .digest('hex')
    .slice(0, 16);

  reply.header('Cache-Control', 'public, max-age=60');
  reply.header('ETag', `"${etag}"`);
  return reply.send(config);
});
```

---

## Profile before optimizing — clinic.js

Never optimize without data. Use `clinic.js` to diagnose event loop stalls and CPU hotspots
before making any performance changes.

```bash
npm install -g clinic

# Detect event loop stalls
clinic doctor -- node dist/server.js

# Flame graph for CPU hotspots
clinic flame -- node dist/server.js

# Then load test with autocannon
autocannon -c 100 -d 30 http://localhost:3000/users
```

The flame graph identifies the actual hotspot. A blocking `JSON.parse` in a rarely-called
route is not worth optimizing; a blocking regular expression in a middleware called on every
request is.

---

## Cache invalidation strategies

Stale cache data is a correctness bug, not just a performance issue. The right invalidation
strategy depends on how often data changes and how stale is acceptable.

### Redis versioning pattern — simplest correct approach

Each cache key includes an entity version counter. On mutation, increment the counter. The old
keys expire naturally via TTL — no explicit deletion needed, no race conditions.

```ts
// CORRECT — version-keyed cache; old keys become orphaned and expire via TTL
async function getUserCached(userId: string): Promise<User> {
  // 1. Get the current version for this user
  const version = await redis.get(`user-version:${userId}`) ?? '1';
  const cacheKey = `user:${userId}:v${version}`;

  // 2. Try cache hit
  const cached = await redis.get(cacheKey);
  if (cached) return JSON.parse(cached) as User;

  // 3. Cache miss — fetch from DB and store with version
  const user = await prisma.user.findUniqueOrThrow({ where: { id: userId } });
  await redis.set(cacheKey, JSON.stringify(user), 'EX', 60 * 60);  // 1h TTL
  return user;
}

// On mutation — bump the version; old cache key becomes unreachable
async function updateUser(userId: string, data: UserUpdate): Promise<User> {
  const user = await prisma.user.update({ where: { id: userId }, data });
  await redis.incr(`user-version:${userId}`);  // cache miss guaranteed on next read
  return user;
}
```

### Stale-while-revalidate — serve stale, refresh in background

For data where brief staleness is acceptable (feature flags, user preferences), serve the cached
value immediately while triggering an async refresh. Eliminates cache-miss latency from the
user's perspective.

```ts
// CORRECT — two TTLs: soft (serve fresh) and hard (must refresh)
interface CacheEntry<T> {
  data: T;
  softExpiresAt: number;   // epoch ms — serve immediately but trigger background refresh
  hardExpiresAt: number;   // epoch ms — must block and refresh
}

async function getWithSwr<T>(
  key: string,
  fetch: () => Promise<T>,
  softTtlMs = 5 * 60 * 1000,        // 5 minutes
  hardTtlMs = 60 * 60 * 1000,       // 1 hour
): Promise<T> {
  const raw = await redis.get(key);

  if (raw) {
    const entry = JSON.parse(raw) as CacheEntry<T>;
    const now = Date.now();

    if (now < entry.softExpiresAt) {
      return entry.data;             // fresh — return immediately
    }

    if (now < entry.hardExpiresAt) {
      // Stale but not expired — return immediately, refresh in background
      void refresh(key, fetch, softTtlMs, hardTtlMs);
      return entry.data;
    }
  }

  // Hard miss or expired — must block
  return refresh(key, fetch, softTtlMs, hardTtlMs);
}

async function refresh<T>(key: string, fetch: () => Promise<T>, softTtlMs: number, hardTtlMs: number): Promise<T> {
  const data = await fetch();
  const now = Date.now();
  const entry: CacheEntry<T> = {
    data,
    softExpiresAt: now + softTtlMs,
    hardExpiresAt: now + hardTtlMs,
  };
  await redis.set(key, JSON.stringify(entry), 'PX', hardTtlMs);
  return data;
}
```

### Cache stampede prevention — distributed lock on miss

When a hot cache key expires, all concurrent requests miss at the same time and hammer the
database simultaneously ("thundering herd"). A distributed lock ensures only one request
refreshes while the others wait briefly for the new value.

```ts
// CORRECT — lock prevents stampede; waiters read the refreshed value
async function getWithStampedePrevention<T>(
  key: string,
  fetch: () => Promise<T>,
  ttlMs: number,
): Promise<T> {
  const cached = await redis.get(key);
  if (cached) return JSON.parse(cached) as T;

  const lockKey = `lock:${key}`;

  // Try to acquire lock — only one worker proceeds; others spin briefly
  const acquired = await redis.set(lockKey, '1', 'NX', 'PX', 10_000);  // 10s lock

  if (!acquired) {
    // Another worker is refreshing — wait and retry
    await new Promise((resolve) => setTimeout(resolve, 200));
    return getWithStampedePrevention(key, fetch, ttlMs);   // retry; will likely hit cache now
  }

  try {
    const data = await fetch();
    await redis.set(key, JSON.stringify(data), 'PX', ttlMs);
    return data;
  } finally {
    await redis.del(lockKey);
  }
}
```
