# Web Frameworks — Node.js Reference

Grounded in **Fastify v5 docs**, **Express docs**, **Hono docs**, and the
**BetterStack Fastify vs Express vs Hono 2025 benchmark**. Fastify is the default
recommendation for new web APIs. Express and Hono are documented as intentional alternatives,
not as equals — choose deliberately.

---

## Framework selection

| Framework | Use when | Why |
|---|---|---|
| **Fastify** | New web APIs and services | 2–3× faster than Express; built-in JSON Schema / TypeBox validation; TypeScript-native; lifecycle hooks; plugin encapsulation |
| **Express** | Legacy codebase or maximum ecosystem reach | Largest middleware ecosystem; most StackOverflow answers; but no built-in validation, slower JSON, error-prone middleware ordering |
| **Hono** | Edge compute / Cloudflare Workers / Bun / Deno | Tiny bundle; zero deps; cross-runtime; identical to Express middleware API; TypeScript-first |
| **`node:http` raw** | Proxies, protocol bridges, very low-level work | No routing abstraction; never use for business logic APIs |

---

## Fastify — the default choice

### Server setup

```ts
// WRONG — no schema validation, no type safety, catches errors manually everywhere
import express from 'express';
const app = express();
app.use(express.json());
app.post('/users', (req, res) => {
  const { email } = req.body;         // unvalidated; could be anything
  res.json({ email });
});
```

```ts
// CORRECT — Fastify with TypeBox schema + type provider
import Fastify from 'fastify';
import { TypeBoxTypeProvider } from '@fastify/type-provider-typebox';
import { Type } from '@sinclair/typebox';

const fastify = Fastify({ logger: true }).withTypeProvider<TypeBoxTypeProvider>();

const CreateUserBody = Type.Object({
  email: Type.String({ format: 'email' }),
  name:  Type.String({ minLength: 1, maxLength: 100 }),
});

fastify.post('/users', { schema: { body: CreateUserBody } }, async (request, reply) => {
  // request.body is fully typed: { email: string; name: string }
  const user = await userService.create(request.body);
  return reply.status(201).send(user);
});
```

### Plugin system — the Fastify architecture unit

Every feature (auth, database, rate-limiting) is a Fastify plugin. Plugins create isolated
scopes; `fastify-plugin` breaks the scope intentionally when you want shared decorators.

```ts
// WRONG — registering everything on the root instance; no encapsulation
fastify.decorate('db', database);
fastify.addHook('onRequest', authHook);
// Every route now has db + auth, even public health checks
```

```ts
// CORRECT — scoped plugin with explicit encapsulation
import fp from 'fastify-plugin';
import type { FastifyPluginAsync } from 'fastify';

// fp() breaks encapsulation — decorators added here are visible on the parent scope
const dbPlugin: FastifyPluginAsync = fp(async (fastify) => {
  const db = await createDatabase(fastify.config.DATABASE_URL);
  fastify.decorate('db', db);
  fastify.addHook('onClose', async () => { await db.close(); });
});

// Without fp() — routes registered inside are isolated from the parent
const userRoutes: FastifyPluginAsync = async (fastify) => {
  fastify.addHook('onRequest', authenticate);   // only applies inside this scope

  fastify.get('/users/:id', async (request, reply) => {
    return fastify.db.getUser(request.params.id);
  });
};

await fastify.register(dbPlugin);
await fastify.register(userRoutes, { prefix: '/api/v1' });
```

### Lifecycle hooks — where each concern lives

Fastify has a well-defined lifecycle. Attach logic at the correct phase:

| Hook | Fires | Use for |
|---|---|---|
| `onRequest` | Before routing | Authentication, request ID injection |
| `preParsing` | Before body parsing | Raw body capture (webhooks), multi-tenancy routing |
| `preValidation` | Before schema validation | Body transformation, format normalization |
| `preHandler` | After validation, before handler | Authorization, business-level guards |
| `onSend` | Before response is serialized | Response mutation, cache headers |
| `onResponse` | After response is sent | Metrics, access logging |
| `onError` | On any thrown error | Structured error shaping, error logging |

```ts
// CORRECT — request ID in onRequest, auth in preHandler
fastify.addHook('onRequest', async (request) => {
  request.id = request.headers['x-request-id'] as string ?? crypto.randomUUID();
});

fastify.addHook('preHandler', async (request, reply) => {
  const token = request.headers.authorization?.replace('Bearer ', '');
  if (!token) return reply.status(401).send({ title: 'Unauthorized', status: 401 });
  request.user = await verifyToken(token);
});
```

### Graceful shutdown — always register

```ts
// WRONG — process killed mid-request; in-flight work is lost
// (no shutdown handler)
```

```ts
// CORRECT — drain in-flight requests before exiting
const shutdown = async (signal: string): Promise<void> => {
  fastify.log.info(`Received ${signal}, shutting down gracefully`);
  await fastify.close();            // stops accepting new requests; drains existing ones
  process.exit(0);
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT',  () => shutdown('SIGINT'));
```

---

## Express — legacy path

If you must use Express, these are the non-negotiable rules:

### Middleware order is critical — document it

```ts
// CORRECT — explicit ordering with comments; security-first
app.use(helmet());                  // 1. Security headers — always first
app.use(cors(corsOptions));         // 2. CORS
app.use(rateLimiter);               // 3. Rate limiting
app.use(express.json({ limit: '1mb' }));  // 4. Body parsing with size limit
app.use(requestIdMiddleware);       // 5. Request ID injection
app.use(authMiddleware);            // 6. Authentication (can be route-scoped instead)
app.use('/api', routes);            // 7. Routes
app.use(errorHandler);              // 8. Centralized error handler — ALWAYS LAST
```

### Async routes must be wrapped

Express does not catch rejected async route handlers. Without a wrapper, a thrown error in an
async handler is an unhandled rejection that crashes the process in Node.js 15+.

```ts
// WRONG — thrown error becomes an unhandled rejection
app.get('/users/:id', async (req, res) => {
  const user = await userService.getById(req.params.id);  // throws → crash
  res.json(user);
});
```

```ts
// CORRECT — asyncHandler forwards rejections to Express error middleware
const asyncHandler =
  (fn: (req: Request, res: Response, next: NextFunction) => Promise<void>) =>
  (req: Request, res: Response, next: NextFunction): void => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };

app.get('/users/:id', asyncHandler(async (req, res) => {
  const user = await userService.getById(req.params.id);
  res.json(user);
}));
```

Express v5 (currently RC) handles async natively — `asyncHandler` is not needed on v5.

---

## Hono — edge and cross-runtime

```ts
// CORRECT — Hono runs on Node.js, Cloudflare Workers, Deno, Bun without changes
import { Hono } from 'hono';
import { zValidator } from '@hono/zod-validator';
import { z } from 'zod';

const app = new Hono();

app.post(
  '/users',
  zValidator('json', z.object({ email: z.string().email(), name: z.string() })),
  async (c) => {
    const { email, name } = c.req.valid('json');
    const user = await userService.create({ email, name });
    return c.json(user, 201);
  }
);

export default app;
```

Hono's middleware API mirrors Express — `c.req`, `c.res`, `await next()`. The `@hono/node-server`
adapter lets it run on Node.js; remove the adapter to deploy to edge.

---

## Response serialization — never JSON.stringify manually

Fastify compiles a JSON serializer at startup from the route schema. `JSON.stringify` is 4–6×
slower. Never call it manually in a Fastify handler.

```ts
// WRONG — bypasses fast-json-stringify; slow; doesn't validate response shape
reply.header('Content-Type', 'application/json').send(JSON.stringify(data));
```

```ts
// CORRECT — Fastify serializes automatically when schema.response is set
fastify.get('/users', {
  schema: {
    response: {
      200: Type.Array(UserSchema),    // compiled serializer; ~4× faster
    },
  },
}, async () => userService.list());
```

---

## Request context — no module-level globals

Per-request state (user, trace ID, tenant) must never be stored in module-level variables.
Node.js processes requests concurrently; a global leaks data between requests.

```ts
// WRONG — concurrent requests overwrite each other's currentUser
let currentUser: User | null = null;

app.use(async (req) => {
  currentUser = await authenticate(req);  // request A sets this; request B overwrites it
});
```

```ts
// CORRECT — AsyncLocalStorage isolates per-request context
import { AsyncLocalStorage } from 'node:async_hooks';

interface RequestContext { user: User; requestId: string; }
const requestContext = new AsyncLocalStorage<RequestContext>();

app.use(async (req, res, next) => {
  const user = await authenticate(req);
  requestContext.run({ user, requestId: req.id }, next);
});

// Anywhere in the call stack — no argument threading needed
function getCurrentUser(): User {
  const ctx = requestContext.getStore();
  if (!ctx) throw new Error('called outside request context');
  return ctx.user;
}
```
