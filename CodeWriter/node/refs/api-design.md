# API Design — Node.js Reference

Grounded in **REST architectural constraints**, **RFC 9457 Problem Details**,
**OpenAPI 3.1 spec**, **@fastify/swagger docs**, **APIs You Won't Hate** (pagination), and
**AppSignal offset vs cursor pagination 2024**. Good API design is a contract — once clients
depend on it, changes must be backward-compatible or versioned.

---

## URL and resource naming

REST URLs identify resources, not actions. HTTP verbs carry the action.

```
# WRONG — verbs in URLs; RPC style
POST /getUser
POST /createOrder
POST /cancelOrder

# CORRECT — nouns identify resources; verbs come from HTTP method
GET    /users/:id
POST   /orders
DELETE /orders/:id
PATCH  /orders/:id    (partial update)
PUT    /orders/:id    (full replacement — rare)
```

| Pattern | URL | Notes |
|---|---|---|
| List | `GET /users` | Paginated; filter via query params |
| Single | `GET /users/:id` | 404 if not found; never 200 with empty body |
| Create | `POST /users` | Returns 201 with created resource; `Location` header optional |
| Partial update | `PATCH /users/:id` | Returns 200 with updated resource |
| Full replace | `PUT /users/:id` | Idempotent; returns 200 or 204 |
| Delete | `DELETE /users/:id` | Returns 204 (no body) or 200 with summary |
| Nested resource | `GET /users/:id/orders` | Owned relationship; max one level deep |
| Action on resource | `POST /orders/:id/cancel` | When no HTTP verb fits; use a noun-based sub-resource |

---

## Response shapes — bare resources over envelopes

Return the resource directly. Wrapping in `{ data: {...} }` adds boilerplate and delays
clients accessing the actual content. Envelopes are needed only for paginated lists.

```ts
// WRONG — unnecessary envelope on every response
res.json({ data: { id: '1', email: 'alice@example.com' }, meta: {} });

// WRONG — list without pagination metadata
res.json([{ id: '1' }, { id: '2' }]);  // client cannot know if there are more
```

```ts
// CORRECT — bare resource for single objects
// GET /users/:id → 200
res.json({ id: '1', email: 'alice@example.com', name: 'Alice' });

// CORRECT — paginated list with metadata
// GET /users → 200
res.json({
  items: [{ id: '1', ... }, { id: '2', ... }],
  nextCursor: 'eyJpZCI6IjIifQ==',   // null if no more pages
  hasMore:    true,
});
```

---

## Pagination — cursor over offset for production APIs

| Strategy | Mechanism | Use when |
|---|---|---|
| **Cursor** | `?cursor=<opaque_token>&limit=50` | Default for most APIs; stable under concurrent inserts; supports infinite scroll |
| **Offset** | `?page=2&limit=50` | Only for small datasets (< 1000 rows) with jump-to-page UX; breaks under concurrent inserts |
| **Keyset** | `?after_id=123&limit=50` | SQL-level cursor; efficient but exposes DB IDs |

**Why offset fails at scale:** `SELECT * FROM users OFFSET 10000 LIMIT 50` must scan and discard
10,000 rows before returning results. At page 1000 of a large dataset, every request is O(n).
Cursor pagination always does an indexed lookup regardless of page number.

```ts
// CORRECT — cursor pagination implementation
import { z } from 'zod';

const PaginationQuery = z.object({
  cursor: z.string().optional(),
  limit:  z.coerce.number().int().min(1).max(100).default(20),
});

fastify.get('/users', async (request, reply) => {
  const { cursor, limit } = PaginationQuery.parse(request.query);

  // Decode cursor (base64-encoded { id: string, createdAt: string })
  const decodedCursor = cursor
    ? JSON.parse(Buffer.from(cursor, 'base64url').toString()) as { id: string }
    : null;

  const users = await prisma.user.findMany({
    take:    limit + 1,              // fetch one extra to detect hasMore
    cursor:  decodedCursor ? { id: decodedCursor.id } : undefined,
    skip:    decodedCursor ? 1 : 0,  // skip the cursor item itself
    orderBy: { createdAt: 'desc' },
    select:  { id: true, email: true, name: true, createdAt: true },
  });

  const hasMore = users.length > limit;
  const items = hasMore ? users.slice(0, limit) : users;
  const lastItem = items.at(-1);

  const nextCursor = hasMore && lastItem
    ? Buffer.from(JSON.stringify({ id: lastItem.id })).toString('base64url')
    : null;

  return reply.send({ items, nextCursor, hasMore });
});
```

**Max page size enforcement:** Always enforce an upper bound on `limit` server-side (e.g. 100).
Never let a client request 10,000 rows in one call.

---

## API versioning — URL path for major breaking changes

```
# CORRECT — URL path versioning; each version is a separate route group
GET /api/v1/users
GET /api/v2/users     ← new response shape; v1 still works

# AVOID — header versioning (Accept: application/vnd.api+json;version=2)
# Harder to test, cache, and document
```

```ts
// CORRECT — version prefix in Fastify
await fastify.register(v1Routes, { prefix: '/api/v1' });
await fastify.register(v2Routes, { prefix: '/api/v2' });

// Deprecation signal on v1 responses
fastify.addHook('onSend', async (request, reply) => {
  if (request.url.startsWith('/api/v1')) {
    reply.header('Deprecation', 'true');
    reply.header('Sunset', 'Sat, 01 Jan 2026 00:00:00 GMT');  // remove date
    reply.header('Link', '</api/v2/users>; rel="successor-version"');
  }
});
```

**Rules:**
- Never make breaking changes in an existing version
- Breaking = removing a field, changing a field type, changing status codes
- Non-breaking = adding optional fields, adding new endpoints, adding new error types
- Deprecate with `Deprecation` + `Sunset` headers; give clients at least 6 months before removal

---

## OpenAPI documentation with @fastify/swagger

Auto-generate OpenAPI 3.1 from Fastify route schemas. No manual YAML maintenance.

```ts
// CORRECT — register swagger plugins
import fastifySwagger from '@fastify/swagger';
import fastifySwaggerUi from '@fastify/swagger-ui';

await fastify.register(fastifySwagger, {
  openapi: {
    openapi: '3.1.0',
    info: { title: 'My API', version: '1.0.0', description: 'API documentation' },
    servers: [{ url: 'https://api.example.com' }],
    components: {
      securitySchemes: {
        BearerAuth: { type: 'http', scheme: 'bearer', bearerFormat: 'JWT' },
      },
    },
  },
});

await fastify.register(fastifySwaggerUi, {
  routePrefix: '/api/docs',            // serve UI at /api/docs
  uiConfig: { docExpansion: 'list' },
});

// Routes with TypeBox schema → auto-documented
fastify.post('/users', {
  schema: {
    tags: ['Users'],
    summary: 'Create a new user',
    security: [{ BearerAuth: [] }],
    body: Type.Object({
      email: Type.String({ format: 'email' }),
      name:  Type.String(),
    }),
    response: {
      201: UserResponseSchema,
      400: ProblemDetailSchema,
    },
  },
}, createUserHandler);

// Generate static OpenAPI JSON for SDK generation
// GET /api/docs/json → OpenAPI 3.1 spec
```

---

## HTTP status codes — use them correctly

The status code is the first signal a client reads. Wrong codes train clients to ignore them.

| Situation | Code |
|---|---|
| Success (no response body) | 204 No Content |
| Created resource | 201 Created |
| Async operation accepted, processing later | 202 Accepted |
| Bad request (validation failure, malformed body) | 400 Bad Request |
| Missing or invalid authentication | 401 Unauthorized |
| Valid auth but insufficient permissions | 403 Forbidden |
| Resource not found | 404 Not Found |
| Method not allowed (`GET /users/:id` with `DELETE`) | 405 Method Not Allowed |
| Conflict (duplicate unique field) | 409 Conflict |
| Business logic rejection (idempotency conflict) | 422 Unprocessable Entity |
| Rate limit exceeded | 429 Too Many Requests |
| Server error | 500 Internal Server Error |
| Downstream dependency unavailable | 503 Service Unavailable |

```ts
// WRONG — 200 with error body; clients cannot branch on the status code
res.status(200).json({ error: 'User not found' });

// CORRECT — semantic status code + RFC 9457 body
throw new NotFoundError('User', userId);
// → 404 + { type: '...', title: 'Not Found', status: 404, detail: 'User xyz not found' }
```

---

## Request IDs and tracing headers

Return the request ID to clients so they can reference it in support requests. Propagate it
to downstream services.

```ts
// CORRECT — echo request ID in response header
fastify.addHook('onSend', async (request, reply) => {
  reply.header('X-Request-Id', request.id);
});

// Propagate to downstream HTTP calls
async function callDownstream(requestId: string, url: string): Promise<Response> {
  return fetch(url, {
    headers: {
      'X-Request-Id': requestId,
      'traceparent': getCurrentTraceParent(),  // W3C Trace Context if using OpenTelemetry
    },
  });
}
```

---

## API rate limit response — `Retry-After` and `X-RateLimit-*` headers

Rate limit responses must include enough information for clients to back off correctly.

```ts
// CORRECT — rate limit headers on 429 responses
await fastify.register(rateLimit, {
  global: true,
  max: 100,
  timeWindow: '1 minute',
  addHeaders: {
    'x-ratelimit-limit':     true,   // max requests
    'x-ratelimit-remaining': true,   // requests remaining in window
    'x-ratelimit-reset':     true,   // Unix timestamp when window resets
    'retry-after':           true,   // seconds to wait before retrying
  },
  errorResponseBuilder: (_req, context) => ({
    type:       'https://errors.example.com/rate-limited',
    title:      'Too Many Requests',
    status:     429,
    detail:     `Rate limit exceeded. Retry after ${context.after}.`,
    retryAfter: context.after,
  }),
});
```
