# Build & CI — TypeScript Frontend Reference

Grounded in the **Vite docs**, the **Next.js docs**, the **TypeScript docs** (tsc CLI), and the
**Lighthouse CI docs**. Deployment containers and pipelines are shared with
`node/refs/devops-and-containers.md`; this file covers the frontend-specific gates.

---

## `tsc --noEmit` is a mandatory CI step

Vite (esbuild/swc) and Next.js **transpile without type-checking** — type errors sail through
`npm run build` unless `tsc` runs. (Next.js runs a check during `next build`, but the explicit
step is faster to fail and works for Vite too.)

```jsonc
// package.json
{
  "scripts": {
    "typecheck": "tsc --noEmit",
    "lint": "eslint .",
    "format:check": "prettier --check .",
    "test": "vitest run",
    "build": "next build"
  }
}
```

---

## CI gate order — fail fast, cheapest first

Same shape as `node/refs/devops-and-containers.md`; Lighthouse appended for the frontend.

```yaml
# .github/workflows/ci.yml (essentials)
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-node@v4
    with: { node-version: 22, cache: npm }
  - run: npm ci                                   # never npm install in CI — lockfile is law
  - run: npm run typecheck                        # 1. types (fast, catches most)
  - run: npm run lint                             # 2. ESLint incl. jsx-a11y
  - run: npm run format:check                     # 3. Prettier
  - run: npm run test                             # 4. Vitest + RTL + axe
  - run: npm audit --audit-level=high             # 5. supply chain
  - run: npm run build                            # 6. production build
  - run: npx lhci autorun                         # 7. Lighthouse budgets (on preview/staging)
```

---

## Path aliases — declared once, mirrored everywhere

`tsconfig.json` `paths` informs the *type-checker* only; the bundler and test runner each need
the same mapping or imports resolve in editors and fail at build.

```jsonc
// tsconfig.json
{ "compilerOptions": { "baseUrl": ".", "paths": { "@/*": ["./src/*"] } } }
```

```ts
// vite.config.ts — mirror for Vite + Vitest
import { fileURLToPath } from 'node:url';
export default defineConfig({
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
});
// (or: vite-tsconfig-paths plugin reads tsconfig automatically)
```

Next.js reads `tsconfig.json` paths natively — no mirror needed. One alias (`@/`) is enough;
an alias zoo (`@components`, `@utils`, `@lib`, …) is churn without benefit.

---

## Bundle size budgets — regressions fail CI

A budget converts "the bundle grew 40% last quarter" from a retro discovery into a failed PR.

```ts
// Vite — warn via chunk limit, enforce via size-limit
export default defineConfig({ build: { chunkSizeWarningLimit: 250 } });
```

```jsonc
// package.json — size-limit makes it a hard gate
{
  "size-limit": [{ "path": "dist/assets/index-*.js", "limit": "180 kB" }],
  "scripts": { "size": "size-limit" }
}
```

For Next.js: `@next/bundle-analyzer` for inspection; track per-route First Load JS from the
`next build` output table (keep it under ~130 kB gzipped per route as a working budget).

---

## Tree shaking hygiene

- Named imports only (`import { debounce } from 'lodash-es'`) — see
  `refs/performance-frontend.md`.
- No side-effectful module top-levels in library code; mark packages `"sideEffects": false`
  when true.
- Dynamic `import()` for anything behind a user decision (modal editors, admin panels,
  export-to-PDF).

---

## Environment variables

| Scope | Pattern |
|---|---|
| Client-embedded | `NEXT_PUBLIC_*` / `VITE_*` — public by definition; build-time inlined |
| Server-only | unprefixed; never imported by client files |

Validate at startup with Zod — same discipline as `node/refs/config-and-secrets.md`:

```ts
// env.ts — import this, never process.env directly in app code
import { z } from 'zod';

const ClientEnvSchema = z.object({
  NEXT_PUBLIC_API_URL: z.string().url(),
});
export const clientEnv = ClientEnvSchema.parse({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,   // must be statically referenced
});
```

Build-time inlining means `process.env[name]` (dynamic access) is `undefined` in the client —
each public var must appear literally.

`.env` is gitignored; `.env.example` is committed with every key and a dummy value.

---

## Lighthouse CI — budgets for the user-facing metrics

```jsonc
// lighthouserc.json
{
  "ci": {
    "collect": { "url": ["http://localhost:3000/"], "startServerCommand": "npm run start" },
    "assert": {
      "assertions": {
        "categories:performance": ["error", { "minScore": 0.9 }],
        "categories:accessibility": ["error", { "minScore": 0.95 }],
        "categories:best-practices": ["error", { "minScore": 0.9 }]
      }
    }
  }
}
```

Run on the preview deployment (Vercel/Netlify URL) or a started production build — never on
the dev server, whose numbers are meaningless.

---

## Production build checks

- `next build` output: no unexpected `ƒ (Dynamic)` routes that should be static — a stray
  `cookies()`/`headers()` call de-statics a whole route.
- Source maps: generate, upload to the error tracker (Sentry), **don't** serve publicly unless
  intentional.
- `next start` (or `vite preview`) locally before merging build-config changes — the dev server
  hides production-only failures (CSP, image domains, env inlining).
