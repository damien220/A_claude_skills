# Security — Node.js Web Reference

Grounded in the **OWASP Node.js Security Cheat Sheet**, **Helmet.js docs**, **OWASP Top 10**,
**RFC 6749 (OAuth 2.0)**, and **Express / Fastify security best practices**. Ruff's analogue
here is `eslint-plugin-security` — install it and treat its findings as errors, not warnings.

---

## HTTP security headers — Helmet.js first

The browser interprets dozens of response headers as security policies. Sending none of them
means the browser applies the least-restrictive defaults. Helmet sets 14+ headers with safe
defaults in one call.

```ts
// WRONG — no security headers; XSS, clickjacking, MIME sniffing all possible
const fastify = Fastify();
// zero security headers on every response
```

```ts
// CORRECT — Fastify: register @fastify/helmet as the first plugin
import helmet from '@fastify/helmet';

await fastify.register(helmet, {
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],       // no inline scripts
      styleSrc: ["'self'", "'unsafe-inline'"],  // adjust per actual style loading
      imgSrc: ["'self'", 'data:'],
    },
  },
  hsts: { maxAge: 31_536_000, includeSubDomains: true },  // 1 year; force HTTPS
});
```

```ts
// CORRECT — Express: use helmet as the first middleware
import helmet from 'helmet';
app.use(helmet());
```

**Headers set by Helmet (partial):**

| Header | Protects against |
|---|---|
| `Content-Security-Policy` | XSS via inline scripts and foreign resources |
| `Strict-Transport-Security` | Downgrade attacks; forces HTTPS for 1 year |
| `X-Frame-Options` | Clickjacking via iframes |
| `X-Content-Type-Options` | MIME type sniffing |
| `Referrer-Policy` | Referrer leakage to external origins |
| `Permissions-Policy` | Geolocation, camera, microphone access |

---

## CORS — explicit origins only

Cross-Origin Resource Sharing must be configured with an explicit allowlist. A wildcard origin
(`*`) is acceptable only for fully public, credential-free APIs (e.g. a public CDN). Never
combine `credentials: true` with `origin: '*'` — browsers block it, but the misconfiguration
signals a misunderstanding of the model.

```ts
// WRONG — wildcard origin with credentials; a malicious site can read responses
app.use(cors({ origin: '*', credentials: true }));
```

```ts
// CORRECT — allowlist from env; credentials only on endpoints that need cookies/auth
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS ?? 'http://localhost:3000')
  .split(',')
  .map((o) => o.trim());

await fastify.register(fastifyCors, {
  origin: ALLOWED_ORIGINS,
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
});
```

Admin and internal API routes: restrict to same-origin (no CORS header means no cross-origin
access) or to an internal IP allowlist at the network layer.

---

## Input validation — Zod everywhere, `safeParse` in handlers

Treat every value crossing a trust boundary (HTTP body, query params, path params, headers,
file contents, environment variables, external API responses) as hostile until validated.

**Rule: Use `safeParse()` in route handlers, never `parse()`.**
`parse()` throws a raw `ZodError`. In a Fastify/Express handler that error hits the error
middleware without an HTTP status code — it becomes a 500 for what should be a 400.

```ts
// WRONG — parse() throws ZodError; becomes 500 unless caught manually
app.post('/users', (req, res) => {
  const body = CreateUserSchema.parse(req.body);   // throws on invalid input
  res.json(body);
});
```

```ts
// CORRECT — safeParse returns a discriminated union; shape the 400 explicitly
import { z } from 'zod';

const CreateUserSchema = z.object({
  email:    z.string().email().toLowerCase().trim(),
  password: z.string().min(12).max(128),
  name:     z.string().min(1).max(100).trim(),
});

fastify.post('/users', async (request, reply) => {
  const result = CreateUserSchema.safeParse(request.body);
  if (!result.success) {
    return reply.status(400).send({
      type: 'https://errors.example.com/validation-error',
      title: 'Validation Error',
      status: 400,
      detail: 'Request body failed validation',
      errors: result.error.flatten().fieldErrors,
    });
  }
  const user = await userService.create(result.data);
  return reply.status(201).send(user);
});
```

For Fastify, prefer TypeBox schemas (JSON Schema) at the route level for request/response
validation and fast serialization. Use Zod for business-logic validation deeper in the stack
(service layer, env vars, external API response shapes).

---

## SQL injection — parameterized queries, always

Never interpolate user input into a SQL string. The database driver always provides a
parameterization mechanism; use it. ESLint `security/detect-sql-injection` flags interpolated
queries.

```ts
// WRONG — any userId value becomes SQL; DROP TABLE is the textbook example
const user = await db.query(`SELECT * FROM users WHERE id = '${userId}'`);
```

```ts
// CORRECT — parameterized; the driver escapes the value, not you
const user = await db.query('SELECT * FROM users WHERE id = $1', [userId]);

// Drizzle ORM — parameterized by construction
const user = await db.select().from(users).where(eq(users.id, userId));

// Prisma — parameterized by construction
const user = await prisma.user.findUnique({ where: { id: userId } });
```

The same applies to all data stores: MongoDB query operators (`$where`, `$regex` with user
input), Redis EVAL scripts with user-supplied Lua, and search index queries.

---

## Rate limiting — protect all public endpoints

Unthrottled endpoints accept unbounded request volume. Auth endpoints are especially sensitive —
a credential-stuffing attack hits `POST /login` thousands of times per second.

```ts
// CORRECT — Fastify with @fastify/rate-limit
import rateLimit from '@fastify/rate-limit';
import Redis from 'ioredis';

await fastify.register(rateLimit, {
  global: true,                        // apply to all routes by default
  max: 100,                            // 100 requests per window
  timeWindow: '1 minute',
  redis: new Redis(env.REDIS_URL),     // Redis store for distributed deployments
  errorResponseBuilder: (_req, context) => ({
    type: 'https://errors.example.com/rate-limited',
    title: 'Too Many Requests',
    status: 429,
    detail: `Rate limit exceeded. Retry after ${context.after}.`,
    retryAfter: context.after,
  }),
});

// Stricter limit on login endpoint
fastify.post('/auth/login', {
  config: { rateLimit: { max: 5, timeWindow: '15 minutes' } },
}, loginHandler);
```

Set `Retry-After` in the 429 response — clients use it to back off correctly.

---

## Authentication — JWT best practices

```ts
// WRONG — long-lived token, stored in localStorage (readable by XSS)
const token = jwt.sign({ userId }, secret, { expiresIn: '30d' });
res.json({ token });                  // client stores in localStorage
```

```ts
// CORRECT — short-lived access token + HttpOnly cookie for refresh token
import { SignJWT, jwtVerify } from 'jose';

const accessToken = await new SignJWT({ sub: userId, role: user.role })
  .setProtectedHeader({ alg: 'RS256' })
  .setIssuedAt()
  .setExpirationTime('15m')           // short-lived access token
  .sign(privateKey);

// Refresh token in HttpOnly + SameSite=Strict cookie — XSS cannot read it
reply.setCookie('refresh_token', refreshToken, {
  httpOnly: true,
  secure: true,
  sameSite: 'strict',
  maxAge: 60 * 60 * 24 * 7,          // 7 days
  path: '/auth/refresh',              // only sent to the refresh endpoint
});

reply.send({ accessToken });          // send access token in body; client stores in memory
```

Use **RS256** (asymmetric) over HS256 (symmetric) for services where verification happens on a
different node than signing — the public key can be distributed without exposing the signing key.

---

## XSS — content security policy + output encoding

```ts
// WRONG — user content stored and reflected without encoding
app.get('/comments/:id', async (req, res) => {
  const comment = await db.getComment(req.params.id);
  res.send(`<p>${comment.body}</p>`);      // injected script executes in browser
});
```

```ts
// CORRECT — use a template engine that auto-escapes, or encode explicitly
import { escape } from 'node:querystring';

// If you must build HTML strings, encode before interpolation
const safeBody = comment.body
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

// Better: never build HTML in route handlers; use a templating engine (Handlebars, Nunjucks)
// or return JSON and let the front-end framework handle rendering.

// For stored rich content: sanitize before persistence with sanitize-html
import sanitizeHtml from 'sanitize-html';
const clean = sanitizeHtml(userHtml, {
  allowedTags: ['b', 'i', 'em', 'strong', 'p'],
  allowedAttributes: {},
});
```

---

## SSRF — validate outbound URLs

```ts
// WRONG — user can supply an internal URL and read metadata endpoints
app.get('/fetch', async (req, res) => {
  const data = await fetch(req.query.url as string);  // fetch http://169.254.169.254/...
  res.json(await data.json());
});
```

```ts
// CORRECT — validate URL against an allowlist or block private ranges
import { isIP } from 'node:net';

function isSafeUrl(raw: string): boolean {
  let url: URL;
  try { url = new URL(raw); } catch { return false; }

  if (!['http:', 'https:'].includes(url.protocol)) return false;

  const host = url.hostname;
  // Block loopback, private ranges, link-local
  if (['localhost', '0.0.0.0'].includes(host)) return false;
  if (host.startsWith('192.168.') || host.startsWith('10.') || host.startsWith('172.')) return false;
  if (host === '169.254.169.254') return false;  // AWS/GCP metadata

  return true;
}

if (!isSafeUrl(req.query.url)) return reply.status(400).send({ title: 'Invalid URL' });
```

---

## Dependency hygiene

```bash
# Run in CI — fail the build if high/critical vulnerabilities exist
npm audit --audit-level=high

# Lock transitive dependencies — always commit package-lock.json
# Use Dependabot or Renovate to automate security updates
```

Never use `npm audit fix --force` blindly — major version bumps break APIs. Review each fix.

---

## CSRF protection — when you need it and how

CSRF is only relevant when authentication state is carried in a **cookie** (session cookies, JWT
in HttpOnly cookie). APIs authenticated with `Authorization: Bearer <token>` in a header are
**not vulnerable to CSRF** — cross-site requests cannot set custom headers.

```
Decision tree:
  Auth via Authorization header (Bearer token)?  → No CSRF needed.
  Auth via HttpOnly cookie?                       → CSRF protection required.
```

### Option A — `SameSite=Strict` (simplest, sufficient for most apps)

`SameSite=Strict` tells the browser never to send the cookie with cross-site requests. This
blocks CSRF by default without any additional token.

```ts
// CORRECT — HttpOnly + SameSite=Strict cookie
reply.setCookie('session', sessionToken, {
  httpOnly:  true,
  secure:    true,               // HTTPS only
  sameSite:  'strict',           // never sent cross-site → CSRF impossible
  maxAge:    60 * 60 * 24 * 7,  // 7 days
  path:      '/',
});
```

**Limitation:** `SameSite=Strict` breaks OAuth2 redirect flows and any cross-domain redirect that
must carry the session. For OAuth2 callback cookies, use `SameSite=Lax`.

### Option B — double-submit CSRF token (when `SameSite=Strict` is not enough)

```ts
// CORRECT — @fastify/csrf-protection double-submit pattern
import fastifyCsrf from '@fastify/csrf-protection';
import fastifyCookie from '@fastify/cookie';

await fastify.register(fastifyCookie, { secret: env.COOKIE_SECRET });
await fastify.register(fastifyCsrf);

// GET /csrf-token — client fetches this and includes in subsequent state-changing requests
fastify.get('/csrf-token', async (request, reply) => {
  const token = reply.generateCsrf();
  return { csrfToken: token };
});

// All POST/PUT/PATCH/DELETE routes — Fastify validates the token automatically
// Client must include: header X-CSRF-Token: <token>  OR  body field _csrf: <token>
```

---

## Authentication architecture — choose deliberately

| Option | When to use | Trade-offs |
|---|---|---|
| **Auth0 / Clerk / Supabase Auth** | Startups, SaaS, teams wanting managed auth | Fast to implement; vendor lock-in; monthly cost at scale |
| **Passport.js + JWT** | Custom auth, specific provider integrations | Full control; more code to maintain; 500+ strategies |
| **Custom JWT + refresh tokens** | When you need specific token claims or flows | Maximum control; must implement rotation, revocation, MFA yourself |
| **NextAuth / Auth.js** | Next.js full-stack apps | Framework-native; limited to Node.js; easy OAuth setup |

For a **production API backend without a managed provider**, the hybrid pattern is the 2025 consensus:
- **Access token:** short-lived JWT (15 min), stateless, verified on every request with no DB lookup
- **Refresh token:** long-lived (7 days), stored as `HttpOnly` cookie, tracked in Redis for revocation

---

## Refresh token rotation and reuse detection

A stolen refresh token can be used indefinitely unless you implement rotation. Each renewal issues
a new refresh token and invalidates the old one. If an old token is replayed, a theft is detected.

```ts
// CORRECT — refresh token rotation with reuse detection
async function refreshTokens(refreshToken: string): Promise<Tokens> {
  // 1. Look up the token family in Redis
  const family = await redis.get(`refresh:${refreshToken}`);
  if (!family) throw new UnauthorizedError('Invalid or expired refresh token');

  const familyData = JSON.parse(family) as { userId: string; version: number };

  // 2. Check if this token has already been used (reuse = theft detected)
  const currentVersion = await redis.get(`refresh-version:${familyData.userId}`);
  if (currentVersion && parseInt(currentVersion) !== familyData.version) {
    // Old token replayed — revoke ALL sessions for this user
    await redis.del(`refresh-version:${familyData.userId}`);
    await redis.del(`session:${familyData.userId}:*`);  // SCAN + DEL in production
    throw new UnauthorizedError('Token reuse detected — all sessions invalidated');
  }

  // 3. Issue new token pair; invalidate old refresh token
  const newVersion = familyData.version + 1;
  await redis.del(`refresh:${refreshToken}`);

  const newRefreshToken = crypto.randomUUID();
  await redis.set(
    `refresh:${newRefreshToken}`,
    JSON.stringify({ userId: familyData.userId, version: newVersion }),
    'EX', 60 * 60 * 24 * 7,   // 7 days
  );
  await redis.set(`refresh-version:${familyData.userId}`, newVersion.toString(), 'EX', 60 * 60 * 24 * 7);

  const accessToken = await signJwt({ sub: familyData.userId });
  return { accessToken, refreshToken: newRefreshToken };
}
```

---

## Account enumeration prevention — identical error messages

Telling an attacker whether an email exists in the system helps them target real accounts.
Auth error messages must be identical whether the account exists or the password is wrong.

```ts
// WRONG — tells attacker whether the email is registered
if (!user) {
  throw new AppError(404, 'No account found with that email');
}
if (!await verifyPassword(password, user.passwordHash)) {
  throw new AppError(401, 'Incorrect password');
}
```

```ts
// CORRECT — identical message regardless of which check failed
const user = await prisma.user.findUnique({ where: { email } });
const passwordValid = user
  ? await bcrypt.compare(password, user.passwordHash)
  : await bcrypt.compare(password, DUMMY_HASH);  // constant-time even if user doesn't exist

if (!user || !passwordValid) {
  throw new UnauthorizedError('Invalid email or password');
}
```

The `DUMMY_HASH` is a bcrypt hash of a random string — it prevents timing attacks that could
identify valid accounts by measuring how long the response takes.
