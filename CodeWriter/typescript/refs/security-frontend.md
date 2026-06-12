# Frontend Security — TypeScript Frontend Reference

Grounded in the **OWASP XSS Prevention Cheat Sheet**, **MDN CSP docs**, the **DOMPurify docs**,
and the **Next.js security headers guide**. Server-side controls live in
`node/refs/security-web.md`; this file covers what the browser bundle is responsible for.

---

## XSS: React escapes JSX — don't open the escape hatch

`{expression}` in JSX is HTML-escaped automatically. The vulnerability surface is exactly the
places that bypass it: `dangerouslySetInnerHTML`, `href`/`src` URLs, and direct DOM writes.

```tsx
// SAFE — React escapes; renders the literal text, not a script tag
<p>{userComment}</p>
```

```tsx
// WRONG — user content straight into innerHTML = stored XSS
<div dangerouslySetInnerHTML={{ __html: userComment }} />
```

```tsx
// CORRECT — rich text is sanitized with an allowlist before injection
import DOMPurify from 'dompurify';

const clean = DOMPurify.sanitize(userComment, {
  ALLOWED_TAGS: ['p', 'b', 'i', 'em', 'strong', 'a', 'ul', 'ol', 'li', 'br'],
  ALLOWED_ATTR: ['href'],
});
<div dangerouslySetInnerHTML={{ __html: clean }} />
```

Every `dangerouslySetInnerHTML` needs a visible justification — the ESLint rule
`react/no-danger` flags each use for review. Markdown pipelines count too: render with a
library that sanitizes (or pipe through DOMPurify), never `marked()` straight into innerHTML.

---

## URL injection — `javascript:` in `href`

React does **not** sanitize URL props. A user-supplied URL rendered into `href` executes on
click.

```tsx
// WRONG — profile.website = "javascript:stealCookies()" executes on click
<a href={profile.website}>Website</a>
```

```tsx
// CORRECT — allowlist the protocol at the validation boundary (Zod) AND at render
const SafeUrl = z
  .string()
  .url()
  .refine((u) => ['https:', 'http:'].includes(new URL(u).protocol), 'Unsupported protocol');

export function safeHref(raw: string): string | undefined {
  try {
    const url = new URL(raw);
    return ['https:', 'http:', 'mailto:'].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

const href = safeHref(profile.website);
{href && <a href={href} target="_blank" rel="noopener noreferrer">Website</a>}
```

`target="_blank"` always pairs with `rel="noopener noreferrer"` — enforced by
`react/jsx-no-target-blank`.

---

## Content Security Policy

CSP is the backstop when an XSS slips through — it blocks inline scripts and unknown origins.
Set it server-side; in Next.js, via `headers()` in `next.config.js` or middleware with a nonce.
(Source: Next.js docs — "Content Security Policy"; MDN CSP.)

```js
// next.config.js — static CSP (use middleware + nonce for stricter setups)
const csp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",     // CSS-in-JS/Tailwind inline styles
  "img-src 'self' data: https:",
  "connect-src 'self' https://api.example.com",
  "frame-ancestors 'none'",               // clickjacking defense
].join('; ');

module.exports = {
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'Content-Security-Policy', value: csp },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ];
  },
};
```

---

## Secrets: nothing private ships to the browser

Every byte of the client bundle is public. `NEXT_PUBLIC_*` / `VITE_*` prefixes mean "embed in
the bundle" — they are a publishing mechanism, not a vault.

```ts
// WRONG — the prefix puts the key in every visitor's hands
const stripe = new Stripe(process.env.NEXT_PUBLIC_STRIPE_SECRET_KEY!);
```

```ts
// CORRECT — secret stays server-side (Server Action / route handler); client gets results
// app/api/checkout/route.ts (server only)
const stripe = new Stripe(env.STRIPE_SECRET_KEY);

// Client-safe values only: publishable keys, public URLs, feature flags
const publishable = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
```

Greppable rule: if the name contains `SECRET`, `PRIVATE`, or `TOKEN`, it must never carry a
public prefix.

---

## Auth tokens: HttpOnly cookies over localStorage

`localStorage` is readable by any script that achieves XSS — token theft is then trivial and
silent. Session/refresh tokens belong in `HttpOnly; Secure; SameSite=Strict` cookies set by the
server (see `node/refs/security-web.md`). The frontend's job: send `credentials: 'include'` and
never persist tokens in JS-readable storage.

```ts
// WRONG
localStorage.setItem('accessToken', token);

// CORRECT — cookie is invisible to JS; CSRF handled by SameSite + server checks
await fetch('/api/session', { method: 'POST', credentials: 'include', body });
```

---

## `eval`, `new Function`, and prototype pollution

- `eval` / `new Function` / string `setTimeout` are banned (`no-eval`, `no-implied-eval`) —
  they turn any injected string into executing code and break CSP.
- Deep-merging unvalidated user objects (`_.merge(config, userInput)`) can pollute
  `Object.prototype` (`__proto__` keys). Zod-validate the shape first; merge only known keys.

```ts
// WRONG — userInput = {"__proto__": {"isAdmin": true}} poisons every object
merge(settings, await req.json());

// CORRECT — schema strips unknown keys, including __proto__
const PatchSchema = z.object({ theme: z.enum(['light', 'dark']), pageSize: z.number() });
const patch = PatchSchema.parse(await res.json());
```

---

## Dependency hygiene

The frontend bundle executes third-party code in your users' browsers — supply chain is part of
your threat model.

```bash
npm audit --audit-level=high          # CI gate — fail the build on high/critical
```

- Renovate or Dependabot for automated patch bumps.
- Pin a lockfile; `npm ci` in CI, never `npm install`.
- Before adding a package: check weekly downloads, maintenance, and whether 10 lines of your
  own code would do (`is-odd` syndrome).
