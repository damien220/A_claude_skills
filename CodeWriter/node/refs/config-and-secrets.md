# Config & Secrets — Node.js Reference

Grounded in the **12-factor app** (factor III: config), **OWASP Secrets Management Cheat Sheet**,
**Zod docs**, and **`@t3-oss/env-core` docs**. The central invariant: secrets live in the
environment, not in source; all environment variables are validated at startup.

---

## Never hardcode secrets in source

API keys, tokens, database passwords, and connection strings must come from the environment.
Source code is committed to version control, printed in logs, and shared with collaborators.
A literal secret is leaked the moment it appears in git history — even if later deleted.

```ts
// WRONG — secret in source; leaked in git history forever
const STRIPE_KEY = 'sk_live_51HxYz...';
const db = postgres({ password: 'hunter2' });
const token = jwt.sign(payload, 'my-super-secret');
```

```ts
// CORRECT — read from env; fail fast if missing
import { env } from './config.js';   // validated config object (see below)

const stripe = new Stripe(env.STRIPE_SECRET_KEY);
const db = postgres({ password: env.DATABASE_PASSWORD });
const token = jwt.sign(payload, env.JWT_SECRET);
```

---

## `.env` for local development — gitignored

Local secrets belong in a `.env` file that is never committed. The `.env.example` file is
committed — it documents every required key with a dummy or description value so collaborators
know what to set up.

```bash
# .gitignore
.env
.env.*
!.env.example
```

```bash
# .env.example — commit this; it is documentation, not secrets
DATABASE_URL=postgres://user:password@localhost:5432/myapp
STRIPE_SECRET_KEY=sk_test_...          # get from Stripe dashboard
JWT_SECRET=<generate with: openssl rand -hex 32>
LOG_LEVEL=info
PORT=3000
NODE_ENV=development
```

```ts
// Entrypoint (server.ts) — load .env before everything else
import 'dotenv/config';    // loads .env into process.env; no-op if file absent
import { env } from './config.js';
```

In production, real environment variables are injected by the platform (Fly.io `flyctl secrets`,
AWS SSM, Doppler, Kubernetes Secrets). `dotenv` is never imported in production code paths.

---

## Validate all env vars at startup — fail fast, fail loudly

A missing or malformed env var discovered at runtime (in a request handler) causes a 500 error
and an unclear log. Validate at startup so the process exits with a clear error message before
accepting any traffic.

```ts
// WRONG — scattered process.env calls; missing var discovered at runtime
app.post('/payment', async (req) => {
  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);  // what if undefined?
  // crashes with "The `apiKey` option is required" mid-request
});
```

```ts
// CORRECT — validate at module load time; startup fails with a clear message
// config.ts
import { z } from 'zod';

const EnvSchema = z.object({
  NODE_ENV:           z.enum(['development', 'production', 'test']).default('development'),
  PORT:               z.coerce.number().int().min(1).max(65535).default(3000),
  DATABASE_URL:       z.string().url(),
  STRIPE_SECRET_KEY:  z.string().startsWith('sk_'),
  JWT_SECRET:         z.string().min(32),
  ALLOWED_ORIGINS:    z.string().default('http://localhost:3000'),
  LOG_LEVEL:          z.enum(['trace', 'debug', 'info', 'warn', 'error', 'fatal']).default('info'),
});

const result = EnvSchema.safeParse(process.env);
if (!result.success) {
  console.error('Invalid environment configuration:');
  console.error(result.error.flatten().fieldErrors);
  process.exit(1);     // exit before the server starts; clear diagnostic message
}

export const env = result.data;
// env.PORT is number; env.NODE_ENV is a literal union; env.DATABASE_URL is string
```

---

## Single `env` object — no scattered `process.env` calls

Accessing `process.env.FOO` directly throughout the codebase creates hidden dependencies on the
environment that are impossible to mock in tests and easy to misspell.

```ts
// WRONG — process.env scattered through application code
// user-service.ts
const DB_TIMEOUT = parseInt(process.env.DB_TIMEOUT_MS ?? '5000');

// payment-service.ts
const apiKey = process.env.STRIPE_SECRET_KEY;   // could be undefined; no validation
```

```ts
// CORRECT — all env access goes through the validated config module
// config.ts exports `env`; every module imports from config.ts
import { env } from './config.js';

const DB_TIMEOUT = env.DB_TIMEOUT_MS;   // typed number, validated at startup
const apiKey = env.STRIPE_SECRET_KEY;   // typed string, guaranteed non-empty
```

---

## Secret wrapper type — prevent accidental logging

Wrap secret values in a type whose `toString()` and `toJSON()` return a placeholder. This
prevents secrets from appearing in logs, error messages, or serialized objects.

```ts
// CORRECT — Secret class; cannot be accidentally logged or serialized
export class Secret<T extends string = string> {
  readonly #value: T;

  constructor(value: T) {
    this.#value = value;
  }

  reveal(): T { return this.#value; }

  toString(): string { return '[SECRET]'; }
  toJSON(): string { return '[SECRET]'; }   // JSON.stringify uses toJSON

  [Symbol.for('nodejs.util.inspect.custom')](): string { return 'Secret([REDACTED])'; }
}

// Usage in config
const JwtSecret = new Secret(env.JWT_SECRET);
// logger.info({ secret: JwtSecret }) → { secret: '[SECRET]' }  ✓
// JwtSecret.reveal() used only at signing time
```

---

## `NODE_ENV` — convention, not feature flag

`NODE_ENV` is a coarse signal. It must only control DX concerns (pretty-printing, dev
tooling). Never use `NODE_ENV` to toggle security behaviour — use explicit feature flags instead.

```ts
// WRONG — disables auth based on NODE_ENV; dangerous if NODE_ENV is wrong or absent
if (process.env.NODE_ENV !== 'production') {
  app.use(bypassAuth);
}
```

```ts
// CORRECT — explicit feature flag; must be set intentionally
const DISABLE_AUTH = env.DISABLE_AUTH === true;   // part of EnvSchema as optional boolean
if (DISABLE_AUTH) {
  logger.warn('AUTH DISABLED — only allowed in local development');
  app.use(bypassAuth);
}
```

Accepted `NODE_ENV` values: `'development'`, `'production'`, `'test'` only. Validate with Zod.

---

## Production secret management

For production secrets, never rely on `.env` files. Use a managed secret store:

| Platform | Tool | How to inject |
|---|---|---|
| AWS | Secrets Manager / Parameter Store | `aws ssm get-parameter` → env at container start |
| GCP | Secret Manager | Workload Identity → SDK at runtime |
| Fly.io | `flyctl secrets set` | Env vars injected automatically at deploy |
| Kubernetes | Kubernetes Secrets | Mounted as env vars in Pod spec |
| Self-hosted | HashiCorp Vault | Vault Agent sidecar or direct SDK |
| Any platform | Doppler | Doppler CLI injects at process start |

Rotate secrets regularly. Validate that the app starts cleanly after rotation with a canary
deploy before fully rolling out.

---

## CORS origins from config

Never hardcode origin lists. They change between environments and belong in config.

```ts
// WRONG — hardcoded list; can't differ between staging and production
const corsOptions = { origin: ['https://myapp.com', 'https://staging.myapp.com'] };
```

```ts
// CORRECT — from env, split on comma, trimmed
// EnvSchema
ALLOWED_ORIGINS: z.string().default('http://localhost:3000'),

// In app setup
const origins = env.ALLOWED_ORIGINS.split(',').map((o) => o.trim());
await fastify.register(fastifyCors, { origin: origins, credentials: true });
```

---

## Secrets never reach logs or error messages

```ts
// WRONG — token appears in log; anyone with log access has the credential
const response = await fetch(apiUrl, {
  headers: { Authorization: `Bearer ${apiKey}` },
});
logger.info({ url: apiUrl, apiKey }, 'API call made');   // apiKey in structured log
throw new Error(`Auth failed for token ${apiKey}`);      // apiKey in error message / stack
```

```ts
// CORRECT — log the action, not the credential
logger.info({ url: apiUrl }, 'API call made');
if (!response.ok) {
  throw new AppError(502, 'Authentication to payment API failed (token redacted)');
}
```
