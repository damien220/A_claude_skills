# Async Patterns — Node.js Reference

Grounded in **Node.js async docs**, **MDN Promises**, **Node.js Streams API**, and the
**WHATWG AbortController spec** (stable in Node.js 16.5+). The central rule: every `Promise`
must be handled; a floating promise is a silent bug that either crashes the process or silently
swallows failures.

---

## `async/await` — always over `.then()` chains

`async/await` is syntactic sugar over Promises but dramatically improves readability,
debuggability (readable stack traces), and error handling (try/catch works naturally).

```ts
// WRONG — .then() chains: hard to read, easy to miss a .catch(), confusing stack traces
function loadUser(id: string) {
  return db.getUser(id)
    .then((user) => validate(user))
    .then((user) => enrich(user))
    .catch((err) => { console.error(err); return null; });
}
```

```ts
// CORRECT — async/await: sequential, readable, debuggable
async function loadUser(id: string): Promise<EnrichedUser | null> {
  try {
    const user = await db.getUser(id);
    const validated = await validate(user);
    return await enrich(validated);
  } catch (err: unknown) {
    logger.error({ err }, 'failed to load user');
    return null;
  }
}
```

---

## `Promise.all` vs `Promise.allSettled` vs `Promise.any`

Choosing the wrong combinator is a common source of silent failures.

| Combinator | Settles when | Use when |
|---|---|---|
| `Promise.all(promises)` | All fulfill **or** first rejects | All promises must succeed; short-circuit on failure is desired |
| `Promise.allSettled(promises)` | All settle (fulfilled or rejected) | Partial success is acceptable; need the full result set |
| `Promise.any(promises)` | First fulfills; rejects if all reject | Race for the first success; fallback chains |
| `Promise.race(promises)` | First settles (fulfilled or rejected) | Timeout races: `Promise.race([fetch(url), timeout(5000)])` |

```ts
// WRONG — Promise.all fails silently if one notification fails; others are not checked
await Promise.all([sendEmail(user), sendSms(user), sendPushNotification(user)]);
```

```ts
// CORRECT — Promise.allSettled: all three run; failures are logged individually
const results = await Promise.allSettled([
  sendEmail(user),
  sendSms(user),
  sendPushNotification(user),
]);

for (const [index, result] of results.entries()) {
  if (result.status === 'rejected') {
    logger.warn({ err: result.reason, index }, 'notification failed');
  }
}
```

```ts
// CORRECT — Promise.any for fallback: try primary CDN, fall back to secondary
const image = await Promise.any([
  fetchFromPrimaryCdn(path),
  fetchFromSecondaryCdn(path),
]).catch(() => { throw new AppError(503, 'All CDN origins failed'); });
```

---

## Floating promises — the silent crash

A floating promise is a `Promise` that is neither `await`-ed nor `.catch()`-ed. If it rejects,
the rejection is unhandled. In Node.js 15+ this terminates the process.

ESLint rule: `@typescript-eslint/no-floating-promises` — treat as an error.

```ts
// WRONG — fire-and-forget; if sendWelcomeEmail() rejects, process crashes
app.post('/users', async (req, res) => {
  const user = await userService.create(req.body);
  sendWelcomeEmail(user);             // floating promise — no await, no .catch()
  res.status(201).json(user);
});
```

```ts
// CORRECT (option A) — await it; request waits for email
const user = await userService.create(req.body);
await sendWelcomeEmail(user);
reply.status(201).send(user);

// CORRECT (option B) — explicit fire-and-forget with error handling
const user = await userService.create(req.body);
void sendWelcomeEmail(user).catch((err) => logger.warn({ err }, 'welcome email failed'));
reply.status(201).send(user);

// 'void' tells ESLint the floating promise is intentional; the .catch() ensures no crash
```

---

## AbortController — cancellable operations

`AbortController` is the standard mechanism for cancelling async operations — fetch, DB queries,
long-running computations. Pass the `signal` through the entire call chain.

```ts
// WRONG — no cancellation; if the client disconnects, the DB query keeps running
fastify.get('/users', async (request) => {
  return userService.listAll();     // cannot be cancelled; leaks DB connection time
});
```

```ts
// CORRECT — AbortController tied to request lifecycle
fastify.get('/users', async (request, reply) => {
  const controller = new AbortController();

  // Abort if the HTTP connection closes before we respond
  request.raw.on('close', () => {
    if (!reply.sent) controller.abort();
  });

  // Pass signal to DB query (pg, Prisma, fetch all accept { signal })
  const users = await userService.listAll({ signal: controller.signal });
  return users;
});
```

```ts
// CORRECT — timeout with AbortController
async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, { signal: controller.signal });
    return response;
  } catch (err) {
    if ((err as Error).name === 'AbortError') {
      throw new AppError(504, `Request to ${url} timed out after ${timeoutMs}ms`);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}
```

---

## Streams — large data without memory exhaustion

Buffering a large response into memory blocks the event loop and risks OOM crashes. Pipe streams
for anything that can be large: file downloads, large DB result sets, HTTP proxy responses.

```ts
// WRONG — entire file loaded into memory; blocks for large files
app.get('/files/:name', async (req, res) => {
  const data = await fs.promises.readFile(`./uploads/${req.params.name}`);  // entire file in RAM
  res.send(data);
});
```

```ts
// CORRECT — stream directly to the response; memory stays O(chunk size)
import { createReadStream } from 'node:fs';
import { pipeline } from 'node:stream/promises';

app.get('/files/:name', async (req, res) => {
  const filePath = path.join('./uploads', path.basename(req.params.name)); // prevent path traversal
  const fileStream = createReadStream(filePath);
  res.setHeader('Content-Type', 'application/octet-stream');

  await pipeline(fileStream, res);    // pipeline handles backpressure and cleanup
});
```

```ts
// CORRECT — transform stream: decompress + count bytes without buffering
import { createGunzip } from 'node:zlib';
import { Transform } from 'node:stream';

let byteCount = 0;
const counter = new Transform({
  transform(chunk, _encoding, callback) {
    byteCount += chunk.length;
    callback(null, chunk);
  },
});

await pipeline(fileStream, createGunzip(), counter, res);
logger.info({ byteCount }, 'file served');
```

Use `stream/promises.pipeline` (not the callback version) — it properly propagates errors and
cleans up all streams in the pipeline on failure.

---

## Concurrency limiting — bounded parallel work

Spawning thousands of Promises in `Promise.all` exhausts the DB connection pool, file descriptor
limit, or external API rate limits.

```ts
// WRONG — 10,000 concurrent DB inserts; exhausts the connection pool
const ids = await db.getUserIds();       // 10,000 rows
await Promise.all(ids.map((id) => processUser(id)));   // 10,000 concurrent queries
```

```ts
// CORRECT — p-limit to cap concurrency
import pLimit from 'p-limit';

const limit = pLimit(10);               // max 10 concurrent operations
const ids = await db.getUserIds();

await Promise.all(ids.map((id) => limit(() => processUser(id))));
// At any moment, at most 10 processUser() calls are in-flight
```

---

## Event emitters — lifecycle and cleanup

`EventEmitter` is appropriate for truly event-driven patterns (file system watchers, WebSocket
messages, process signals). For request-scoped data flow, async generators or callbacks are
simpler.

```ts
// WRONG — listener registered but never removed; memory leak on repeated calls
function monitorFile(path: string): void {
  const watcher = fs.watch(path);
  watcher.on('change', (event) => logger.info({ event, path }, 'file changed'));
  // watcher is never closed; listener count grows indefinitely
}
```

```ts
// CORRECT — use AbortController or explicit cleanup
function monitorFile(path: string, signal: AbortSignal): void {
  const watcher = fs.watch(path, { signal });

  watcher.on('change', (event) => logger.info({ event, path }, 'file changed'));
  watcher.on('error', (err) => logger.error({ err, path }, 'watch error'));

  // AbortController abort causes watcher.close() automatically
}

// Caller controls lifecycle:
const controller = new AbortController();
monitorFile('./config.json', controller.signal);
// Later:
controller.abort();   // watcher closes cleanly
```

Always call `emitter.setMaxListeners(n)` if you legitimately register more than the default 10
listeners — the default warning is a guard against unintentional leaks, not a hard limit.

---

## Top-level `await` in entry points

ESM modules support top-level `await`. Use it to sequence async initialization before the server
starts accepting requests.

```ts
// CORRECT — sequential startup in ESM entry point (server.ts)
import { createApp }    from './app.js';
import { connectDb }    from './db.js';
import { loadConfig }   from './config.js';

const config = await loadConfig();           // validate env vars first
await connectDb(config.DATABASE_URL);        // fail fast if DB unreachable
const app = await createApp(config);
await app.listen({ port: config.PORT, host: '0.0.0.0' });

logger.info({ port: config.PORT }, 'Server started');
```

Never use top-level `await` in library code — it blocks the module graph and may cause
unexpected ordering effects for consumers.
