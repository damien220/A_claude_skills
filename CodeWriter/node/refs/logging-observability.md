# Logging & Observability — Node.js Reference

Grounded in **Pino docs**, **12-factor app** (logs as event streams, factor XI), and
**OpenTelemetry Node.js**. The central rule: structured JSON logs, one logger instance, never
`console.log` in production code.

**Performance baseline:** Pino outputs ~222,000 log entries/sec vs Winston's ~36,000. The gap
comes from async transport (Pino writes off-thread) and fast-json-stringify serialization.

---

## Never `console.log` in production code

`console.log` is synchronous, unstructured, and has no levels, no context binding, and no
redaction. It blocks the event loop on every call.

```ts
// WRONG — synchronous, unstructured, no level, no context
console.log('User logged in:', userId);
console.error('Failed:', err.message);
```

```ts
// CORRECT — Pino: async, structured, leveled
import pino from 'pino';

export const logger = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  // In production: no transport (raw JSON to stdout → aggregator)
  // In dev: pino-pretty for human-readable output
  ...(process.env.NODE_ENV !== 'production' && {
    transport: {
      target: 'pino-pretty',
      options: { colorize: true, singleLine: false },
    },
  }),
});

// Module-level usage
import { logger } from './logger.js';
logger.info({ userId }, 'user logged in');
```

---

## One logger instance — shared or injected

Never create a new `pino()` instance per file. Create once, export, and import. For testability,
inject via constructor parameter; default to the shared instance.

```ts
// WRONG — new pino() per module; config diverges; memory leak
// user-service.ts
const log = pino();     // independent instance; different config possible

// auth-service.ts
const log = pino();     // another independent instance
```

```ts
// CORRECT — single export from logger.ts
// logger.ts
export const logger = pino({ level: process.env.LOG_LEVEL ?? 'info' });

// user-service.ts
import { logger } from './logger.js';
// Use logger directly — or accept a logger parameter for testability:
export class UserService {
  readonly #logger: pino.Logger;
  constructor(private db: Database, log = logger) {
    this.#logger = log.child({ service: 'UserService' });
  }
}
```

---

## Structured bindings first — never string interpolation

Log entries are consumed by aggregators (Datadog, Loki, CloudWatch). Aggregators can filter,
group, and alert on JSON fields. String interpolation produces unqueryable prose.

```ts
// WRONG — string interpolation; "user 42" is unqueryable
logger.info(`User ${userId} logged in from ${ip}`);
logger.error(`Failed to process order ${orderId}: ${err.message}`);
```

```ts
// CORRECT — object first, message second; every field is queryable
logger.info({ userId, ip, action: 'login' }, 'user logged in');
logger.error({ err, orderId }, 'order processing failed');
// pino serializes err.message, err.stack, err.name automatically via built-in serializer
```

---

## Child loggers — propagate per-request context

A child logger inherits the parent's config and adds permanent key-value bindings. Every log
line emitted by that child (or its children) includes the bindings — no argument threading
required.

```ts
// WRONG — requestId manually repeated on every log call; easily forgotten
logger.info({ requestId, userId }, 'starting payment');
await paymentService.charge(amount);
logger.info({ requestId, userId }, 'payment complete');
```

```ts
// CORRECT — child logger carries context automatically
// In Fastify: create child logger per request using onRequest hook
fastify.addHook('onRequest', (request, _reply, done) => {
  // Fastify injects request.log automatically (uses child with reqId binding)
  // For custom context, create a child and store on request:
  request.log = request.log.child({ userId: request.user?.id });
  done();
});

// Any code that receives request.log gets userId bound for free
request.log.info('starting payment');
await paymentService.charge(amount, { log: request.log });
request.log.info('payment complete');
```

```ts
// CORRECT — AsyncLocalStorage for context without passing logger everywhere
import { AsyncLocalStorage } from 'node:async_hooks';
import type pino from 'pino';

const loggerStore = new AsyncLocalStorage<pino.Logger>();

export function getLogger(): pino.Logger {
  return loggerStore.getStore() ?? logger;   // fallback to root logger outside request
}

// In middleware: run the rest of the request inside a child logger context
fastify.addHook('onRequest', (request, _reply, done) => {
  const child = logger.child({ requestId: request.id, method: request.method, url: request.url });
  loggerStore.run(child, done);
});
```

---

## Log levels — choose deliberately

| Level | pino method | Use for |
|---|---|---|
| `trace` | `logger.trace()` | Very fine-grained; DB query parameters, raw HTTP bodies — dev only |
| `debug` | `logger.debug()` | Internal state useful for debugging; disabled in production by default |
| `info` | `logger.info()` | Normal operations: request received, user action, service state change |
| `warn` | `logger.warn()` | Recoverable unexpected event: retried request succeeded, fallback used |
| `error` | `logger.error()` | Failure that needs attention but did not crash the process |
| `fatal` | `logger.fatal()` | Process-stopping failure; always followed by `process.exit(1)` |

```ts
// WRONG — wrong levels; everything at the same level; no signal vs noise distinction
logger.info('DB connection failed, retrying');    // should be warn or error
logger.error('User changed their password');      // should be info
```

```ts
// CORRECT
logger.warn({ attempt, err }, 'DB connection failed, retrying');
logger.info({ userId }, 'user changed password');
logger.error({ err, orderId }, 'payment processing failed — manual review required');
logger.fatal({ err }, 'could not bind to port — exiting');
process.exit(1);
```

---

## Secrets and PII must never appear in logs

Log entries are stored, indexed, and searched by aggregators. A secret in a log line is a
breach the moment it reaches any log store. Use Pino's `redact` option to strip known paths.

```ts
// WRONG — token logged; anyone with log access has the credential
logger.info({ headers: request.headers, body: request.body }, 'incoming request');
// request.headers.authorization = 'Bearer sk_live_...'
// request.body.password = 'hunter2'
```

```ts
// CORRECT — redact known sensitive paths at logger creation
export const logger = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  redact: {
    paths: [
      'req.headers.authorization',
      'req.headers.cookie',
      'body.password',
      'body.token',
      'body.secret',
      '*.creditCard',
      '*.ssn',
    ],
    censor: '[REDACTED]',
  },
});

// For dynamic secrets, wrap in a type that cannot be serialized
class Secret {
  readonly #value: string;
  constructor(value: string) { this.#value = value; }
  reveal(): string { return this.#value; }
  toJSON(): string { return '[SECRET]'; }    // JSON.stringify uses toJSON
  toString(): string { return '[SECRET]'; }
}
```

---

## Request logging — use framework integration

Do not write manual request/response logging middleware. Use the framework's native integration
with Pino.

```ts
// CORRECT — Fastify: built-in Pino logger; request + response logged automatically
const fastify = Fastify({
  logger: {
    level: process.env.LOG_LEVEL ?? 'info',
    serializers: {
      req: (req) => ({ method: req.method, url: req.url, id: req.id }),
      res: (res) => ({ statusCode: res.statusCode }),
    },
  },
});

// CORRECT — Express: pino-http middleware
import pinoHttp from 'pino-http';

app.use(pinoHttp({
  logger,
  customLogLevel: (_req, res) => (res.statusCode >= 500 ? 'error' : 'info'),
  serializers: {
    req: (req) => ({ method: req.method, url: req.url, id: req.id }),
  },
}));
```

---

## Correlation IDs — trace a request end to end

Every inbound request must carry a unique `requestId`. Include it in every log line and outbound
call header so the full request trace is reconstructable across services.

```ts
// CORRECT — inject requestId in first hook; propagate via child logger
import { randomUUID } from 'node:crypto';

fastify.addHook('onRequest', (request, _reply, done) => {
  // Accept an existing trace ID from an upstream service, or generate a new one
  request.id = (request.headers['x-request-id'] as string) ?? randomUUID();
  done();
});

// Propagate to outbound calls
async function callDownstreamService(requestId: string): Promise<Data> {
  const response = await fetch('https://internal-service/data', {
    headers: { 'x-request-id': requestId },   // carry the trace across service boundaries
  });
  return response.json() as Promise<Data>;
}
```

---

## Production transport — JSON only, no pino-pretty

`pino-pretty` is for development terminals. In production it adds ~40% overhead and produces
human-readable output that is harder to parse by log aggregators.

```ts
// CORRECT — production logger: raw JSON to stdout; aggregator handles formatting
export const logger = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  // no transport — pino writes directly to stdout as JSON
  // run with: node server.js | pino-pretty (dev) OR pipe to aggregator (prod)
});

// CI / staging shortcut — pretty-print without redeploying:
// LOG_PRETTY=1 node server.js  — check process.env.LOG_PRETTY in the logger factory
```

---

## Library code — no logger initialization

Libraries must never call `pino()`, `logger.info()`, or set up any transport. Emit nothing by
default; accept an optional `logger` parameter if observability is needed.

```ts
// WRONG — library configures its own logger; collides with app logging setup
export class PaymentClient {
  #logger = pino({ level: 'debug' });    // library imposes its own log config on the app
}
```

```ts
// CORRECT — no-op by default; app can inject its logger if needed
interface Logger {
  info(obj: Record<string, unknown>, msg: string): void;
  error(obj: Record<string, unknown>, msg: string): void;
}

const noopLogger: Logger = { info: () => {}, error: () => {} };

export class PaymentClient {
  readonly #logger: Logger;
  constructor(options: { logger?: Logger } = {}) {
    this.#logger = options.logger ?? noopLogger;
  }
}
```

---

## Health check endpoints — three signals

A proper observability setup exposes three distinct health endpoints. These are distinct from the
logging layer but belong in the observability stack alongside structured logs. See
`refs/devops-and-containers.md` for the Kubernetes probe configuration.

```ts
// CORRECT — lightweight /live; DB-checking /ready; init-checking /startup
fastify.get('/live',  async (_req, reply) => reply.status(200).send({ status: 'ok' }));

fastify.get('/ready', async (_req, reply) => {
  const [db, cache] = await Promise.allSettled([
    prisma.$queryRaw`SELECT 1`,
    redis.ping(),
  ]);
  const errors = [db, cache]
    .filter((r): r is PromiseRejectedResult => r.status === 'rejected')
    .map((r) => r.reason?.message ?? 'unknown');

  return errors.length
    ? reply.status(503).send({ status: 'not ready', errors })
    : reply.status(200).send({ status: 'ready' });
});
```

---

## Prometheus metrics — expose `/metrics`

Prometheus scrapes a `/metrics` endpoint on a fixed interval. Expose at minimum: request counts,
latency histogram, and process uptime. Add domain metrics for key business events.

```ts
// CORRECT — prom-client with Fastify
import { Registry, collectDefaultMetrics, Counter, Histogram } from 'prom-client';

const register = new Registry();
collectDefaultMetrics({ register });   // adds process CPU, memory, GC, event loop lag

// Custom domain metrics
export const httpRequestsTotal = new Counter({
  name: 'http_requests_total',
  help: 'Total HTTP request count',
  labelNames: ['method', 'route', 'status_code'],
  registers: [register],
});

export const httpRequestDuration = new Histogram({
  name: 'http_request_duration_seconds',
  help: 'HTTP request duration in seconds',
  labelNames: ['method', 'route', 'status_code'],
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5],
  registers: [register],
});

// Hook to record every request
fastify.addHook('onResponse', async (request, reply) => {
  const route = request.routeOptions?.url ?? request.url;
  const labels = { method: request.method, route, status_code: reply.statusCode };

  httpRequestsTotal.inc(labels);
  httpRequestDuration.observe(labels, reply.elapsedTime / 1000);
});

// Expose metrics endpoint — restrict to internal network or auth in production
fastify.get('/metrics', async (_request, reply) => {
  reply.header('Content-Type', register.contentType);
  return reply.send(await register.metrics());
});
```

---

## OpenTelemetry — distributed tracing basics

For microservices or when you need request traces across multiple services, OpenTelemetry
provides vendor-neutral instrumentation. Initialize before any other imports.

```ts
// CORRECT — tracing.ts — must be the FIRST import in server.ts
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { SEMRESATTRS_SERVICE_NAME } from '@opentelemetry/semantic-conventions';

const sdk = new NodeSDK({
  resource: new Resource({ [SEMRESATTRS_SERVICE_NAME]: 'my-api' }),
  traceExporter: new OTLPTraceExporter({ url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT }),
  instrumentations: [getNodeAutoInstrumentations()],   // auto-instruments http, pg, redis, etc.
});

sdk.start();

process.on('SIGTERM', async () => {
  await sdk.shutdown();
});
```

```ts
// server.ts — tracing MUST be initialized before framework imports
import './tracing.js';    // first import
import Fastify from 'fastify';
// ...
```

**Manual spans for business logic:**
```ts
import { trace, SpanStatusCode } from '@opentelemetry/api';

const tracer = trace.getTracer('my-api');

async function chargeCustomer(customerId: string, amount: number): Promise<void> {
  const span = tracer.startSpan('payment.charge', {
    attributes: { 'payment.customer_id': customerId, 'payment.amount': amount },
  });
  try {
    await stripeClient.charge({ customerId, amount });
    span.setStatus({ code: SpanStatusCode.OK });
  } catch (err) {
    span.recordException(err as Error);
    span.setStatus({ code: SpanStatusCode.ERROR });
    throw err;
  } finally {
    span.end();
  }
}
```

W3C Trace Context headers (`traceparent`, `tracestate`) are propagated automatically by the
auto-instrumentation for all outbound `fetch` and `http` requests.
