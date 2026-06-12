# Error Handling — Node.js Web Reference

Grounded in **RFC 9457** (Problem Details for HTTP APIs), the **Express error handling guide**,
**Fastify error handling docs**, and **Node.js unhandled rejection behavior** (process exit since
Node.js 15+). The central invariant: errors are caught in one place, logged with full context,
and returned to clients in a standard, safe format that never exposes internals.

---

## RFC 9457 — the error response format

Every HTTP error response must follow RFC 9457 (Problem Details). This is a IETF standard that
makes error responses machine-readable, consistent, and safe (no stack traces).

```ts
// WRONG — ad hoc error shapes; every endpoint invents its own format
res.status(400).json({ message: 'invalid email' });
res.status(404).json({ error: true, msg: 'not found' });
res.status(500).json({ message: err.message, stack: err.stack });  // leaks internals
```

```ts
// CORRECT — RFC 9457 Problem Details; consistent across the entire API
// Content-Type: application/problem+json

interface ProblemDetail {
  type: string;        // URI identifying the error category (docs link)
  title: string;       // human-readable summary of the category
  status: number;      // HTTP status code
  detail: string;      // specific, human-readable explanation for this occurrence
  instance?: string;   // URI of the specific request (e.g. req.url)
  [extension: string]: unknown;  // domain-specific extensions
}

// Example responses:
// 400: { type: 'https://api.example.com/errors/validation', title: 'Validation Error',
//         status: 400, detail: 'email must be a valid address', instance: '/users' }
// 404: { type: 'https://api.example.com/errors/not-found', title: 'Not Found',
//         status: 404, detail: 'User with ID abc123 not found', instance: '/users/abc123' }
// 500: { type: 'about:blank', title: 'Internal Server Error',
//         status: 500, detail: 'An unexpected error occurred', instance: '/users' }
//       ← never expose the real cause in 500s; log it server-side
```

---

## `AppError` — typed application errors

Define a hierarchy of typed errors so the central handler can make policy decisions without
`instanceof` chains.

```ts
// CORRECT — base AppError + domain-specific subclasses
export class AppError extends Error {
  constructor(
    public readonly statusCode: number,
    public readonly detail: string,
    public readonly type: string = 'about:blank',
    options?: ErrorOptions,           // { cause: originalError }
  ) {
    super(detail, options);
    this.name = this.constructor.name;
    Error.captureStackTrace(this, this.constructor);
  }
}

export class NotFoundError extends AppError {
  constructor(resource: string, id: string) {
    super(404, `${resource} with ID ${id} not found`,
      'https://api.example.com/errors/not-found');
  }
}

export class ValidationError extends AppError {
  constructor(detail: string, public readonly fields?: Record<string, string[]>) {
    super(400, detail, 'https://api.example.com/errors/validation');
  }
}

export class UnauthorizedError extends AppError {
  constructor(detail = 'Authentication required') {
    super(401, detail, 'https://api.example.com/errors/unauthorized');
  }
}
```

---

## Centralized error handler — Fastify

Fastify has a built-in error handler mechanism. Register it once; all thrown errors funnel
through it.

```ts
// CORRECT — Fastify setErrorHandler
import type { FastifyError, FastifyReply, FastifyRequest } from 'fastify';
import { ZodError } from 'zod';

fastify.setErrorHandler(
  (error: FastifyError | AppError | Error, request: FastifyRequest, reply: FastifyReply) => {
    // Log full error including stack — never send this to the client
    request.log.error({ err: error, url: request.url }, 'Request failed');

    // Zod validation error → 400
    if (error instanceof ZodError) {
      return reply.status(400).contentType('application/problem+json').send({
        type: 'https://api.example.com/errors/validation',
        title: 'Validation Error',
        status: 400,
        detail: 'Request body failed schema validation',
        instance: request.url,
        errors: error.flatten().fieldErrors,
      });
    }

    // Known application error
    if (error instanceof AppError) {
      return reply.status(error.statusCode).contentType('application/problem+json').send({
        type: error.type,
        title: error.name,
        status: error.statusCode,
        detail: error.detail,
        instance: request.url,
      });
    }

    // Fastify schema validation error (when using JSON Schema / TypeBox)
    if ('statusCode' in error && error.statusCode === 400) {
      return reply.status(400).contentType('application/problem+json').send({
        type: 'https://api.example.com/errors/validation',
        title: 'Validation Error',
        status: 400,
        detail: error.message,
        instance: request.url,
      });
    }

    // Unknown error — never leak internals
    return reply.status(500).contentType('application/problem+json').send({
      type: 'about:blank',
      title: 'Internal Server Error',
      status: 500,
      detail: 'An unexpected error occurred. Please try again later.',
      instance: request.url,
    });
  }
);
```

---

## Centralized error handler — Express

Express error middleware takes four arguments — `(err, req, res, next)`. The fourth argument
is what makes Express recognize it as an error handler; omitting it silently turns it into
regular middleware.

```ts
// WRONG — three-arg "error handler" is just regular middleware; errors bypass it
app.use((err: Error, res: Response) => {
  res.status(500).json({ message: err.message });
});
```

```ts
// CORRECT — four-arg error handler; register AFTER all routes
import type { ErrorRequestHandler } from 'express';

const errorHandler: ErrorRequestHandler = (err, req, res, _next) => {
  const log = req.app.locals.logger ?? console;
  log.error({ err, url: req.url }, 'Request failed');

  if (err instanceof AppError) {
    res.status(err.statusCode).contentType('application/problem+json').json({
      type: err.type,
      title: err.name,
      status: err.statusCode,
      detail: err.detail,
      instance: req.url,
    });
    return;
  }

  res.status(500).contentType('application/problem+json').json({
    type: 'about:blank',
    title: 'Internal Server Error',
    status: 500,
    detail: 'An unexpected error occurred.',
    instance: req.url,
  });
};

app.use(errorHandler);   // after all app.use(routes)
```

---

## Async error propagation — Express

```ts
// WRONG — rejected promise is an unhandled rejection; process crashes (Node 15+)
app.get('/users/:id', async (req, res) => {
  const user = await userService.getById(req.params.id);   // throws → unhandled
  res.json(user);
});
```

```ts
// CORRECT — asyncHandler forwards the rejection to Express error middleware
const asyncHandler =
  (fn: (req: Request, res: Response, next: NextFunction) => Promise<void>) =>
  (req: Request, res: Response, next: NextFunction): void => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };

app.get('/users/:id', asyncHandler(async (req, res) => {
  const user = await userService.getById(req.params.id);
  res.json(user);
}));

// Alternatively: Express v5 (currently RC) handles async natively.
// Fastify: async route handlers are always safe — Fastify wraps them automatically.
```

---

## `unknown` in catch clauses

TypeScript 4.4+ defaults to `unknown` in catch clauses when `useUnknownInCatchVariables`
is on (part of `strict`). Always narrow before accessing properties.

```ts
// WRONG — any gives you no safety
try {
  await riskyOperation();
} catch (err: any) {
  logger.error(err.message);          // crashes if err is a string or null
}
```

```ts
// CORRECT — narrow explicitly
try {
  await riskyOperation();
} catch (err: unknown) {
  if (err instanceof AppError) throw err;              // re-throw known errors
  if (err instanceof Error) {
    throw new AppError(500, 'Internal failure', 'about:blank', { cause: err });
  }
  throw new AppError(500, 'Unknown failure');
}
```

Helper to extract a message safely:
```ts
export function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return 'Unknown error';
}
```

---

## Unhandled rejection and uncaught exception — process exit policy

Node.js 15+ converts unhandled rejections to uncaught exceptions (process crash). Register
handlers that log the error in structured form before exiting — this gives you a last-chance
log entry for the crash.

```ts
// CORRECT — last-chance error capture at the process level
process.on('uncaughtException', (err: Error) => {
  // Log synchronously — the process may be in a bad state
  logger.fatal({ err }, 'Uncaught exception — process is restarting');
  process.exit(1);     // let the process manager (PM2, Kubernetes) restart
});

process.on('unhandledRejection', (reason: unknown) => {
  logger.fatal({ reason }, 'Unhandled promise rejection — process is restarting');
  process.exit(1);
});
```

**Do not** try to recover from `uncaughtException` — the Node.js docs explicitly warn that the
process may be in an inconsistent state. Exit and let a supervisor restart it cleanly.

---

## Stack trace policy — log, never expose

```ts
// WRONG — stack trace in HTTP response; reveals file paths, libraries, internal logic
res.status(500).json({
  error: err.message,
  stack: err.stack,        // attacker learns your framework, file structure, error line
});
```

```ts
// CORRECT — log full context internally; return safe generic message to client
logger.error({
  err,              // pino serializes err.message, err.stack, err.name automatically
  requestId: req.id,
  url: req.url,
  userId: req.user?.id,
}, 'Unexpected error');

reply.status(500).send({
  type: 'about:blank',
  title: 'Internal Server Error',
  status: 500,
  detail: 'An unexpected error occurred.',
});
```

The distinction: 4xx errors (client mistakes) can include specific detail about what was wrong
(safe to expose — the client already knows what they sent). 5xx errors (server failures) must
return a generic message; log the real cause.
