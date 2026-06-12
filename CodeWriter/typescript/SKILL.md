---
name: typescript-frontend-best-style
description: Use when writing, editing, refactoring, or reviewing React/TypeScript frontend
  code to produce idiomatic, performant, accessible, and secure UIs. Enforces strict TypeScript,
  React hooks discipline, TanStack Query for server state, Zod API boundary validation, React
  Hook Form + Zod for forms, React Testing Library tests, jsx-a11y accessibility rules, and
  Next.js App Router / RSC best practices. Also handles cloning the look and feel of a reference
  website from a URL or screenshot into a token-driven design implementation. Triggers on
  .tsx/.jsx files, "write a React component", "refactor this hook", "add a form", "best
  practice", "make this idiomatic", "clone the design of <url>", or "make it look like <url>".
---

# TypeScript Frontend Best Style

## Identity & Mission

You write React/TypeScript frontend code that is *idiomatic, performant, accessible, and
secure* — not merely code that renders. Resolve style from the named authoritative source
(React docs, TypeScript handbook, TanStack docs, WCAG, OWASP, Next.js docs, …) and apply the
pattern that fits the task, stating the rationale (readability / performance / safety / a11y)
when it is non-obvious.

**Language baseline:** TypeScript 5.5+ with React 19 (18 minimum). Next.js 15 App Router as
the primary deployment target; Vite for SPAs and libraries. Strict tsconfig shared with the
`node/` skill.

**Idiom is per-language:** `camelCase` for variables/functions/hooks, `PascalCase` for
components/types, `UPPER_SNAKE_CASE` for constants. Never import another language's
conventions.

**How to use this skill.** The titles below are the always-loaded summary — each is an
authoritative rule you can apply directly. Do **not** pre-load the `refs/`. When the current
task matches a title's `Read … when:` trigger, load that one ref for deep guidance (WRONG vs
CORRECT examples, comparison tables, citations), then apply it. Before declaring code done,
run the pre-ship gate (final title).

---

## Titles

### 1. Naming & file layout
Components are `PascalCase` (file matches export); hooks are `use*`; utilities `camelCase.ts`;
directories `kebab-case`. Boolean props read `isLoading`/`hasError`; handler functions are
`handle*`, handler props are `on*`. Co-locate by feature (component + hook + types + tests +
styles in one directory); barrel `index.ts` exposes a deliberate public API, never wildcard
re-exports.
Read **`refs/naming-and-layout.md`** when: naming components, hooks, files, or props; laying
out a feature directory; writing barrel exports; or placing files in Next.js route segments.

### 2. TypeScript strict mode
Always `"strict": true` with `noUncheckedIndexedAccess` and `verbatimModuleSyntax`; frontend
adds `"jsx": "react-jsx"` and DOM libs. Props get an explicit `interface Props` — never `any`,
never `React.FC`. Everything crossing the network or a `catch` is `unknown` until validated.
Type events as `React.ChangeEvent<HTMLInputElement>` etc.; refs as `useRef<HTMLElement>(null)`;
prefer `satisfies` over `as`.
Read **`refs/typescript-strict.md`** when: setting up tsconfig, typing props/children/events/
refs, writing generic components, resolving a strict-mode error, or tempted by `any` or a cast.

### 3. React patterns
`useEffect` is only for synchronizing with external systems — never for derived state (compute
during render) and never for event logic (put it in the handler). Memoize for referential
stability or measured expense only. Keys come from data identity, not array index. Compose
(children, compound components) instead of drilling props; wrap async subtrees in error
boundaries.
Read **`refs/react-patterns.md`** when: designing a component, writing or reviewing a
useEffect, adding useMemo/useCallback/React.memo, rendering lists, or restructuring prop
drilling.

### 4. State management
Classify first: server state → TanStack Query; local UI state → `useState`/`useReducer`;
shared client state → Zustand or Jotai; filters/pagination → the URL. Never copy server data
into `useState` or a store — one source of truth. Context is for low-frequency globals (theme,
user), never high-frequency updates. Subscribe narrowly with selectors.
Read **`refs/state-management.md`** when: choosing where state lives, adding a store, reaching
for Context, syncing props to state, or putting filters/sort in component state.

### 5. Data fetching
`useEffect` data fetching is forbidden in new code — `useQuery` handles cache, dedupe, races,
retries, and abort. The `queryKey` includes every parameter the fetch depends on (use key
factories). Set `staleTime` explicitly. Mutations invalidate related queries in `onSuccess`;
optimistic updates use the `onMutate`/`onError`/`onSettled` rollback contract; dependent
queries gate with `enabled`.
Read **`refs/data-fetching.md`** when: fetching or mutating remote data, designing query keys,
adding optimistic updates, paginating, or handling loading/error states.

### 6. API contracts
Every network response is `unknown` until Zod `safeParse()` validates it — never `as MyType`.
One schema per endpoint, types derived via `z.infer`; a centralized `apiFetch(path, schema)`
wrapper owns validation and typed `ApiError`s. Error bodies are validated too (RFC 9457 shape
from the node skill). In full-stack TS monorepos define schemas once (shared package or tRPC).
Read **`refs/api-contracts.md`** when: calling an API, writing fetch wrappers, defining
response types, handling API errors, sharing types with the backend, or considering tRPC.

### 7. Forms & validation
React Hook Form + `zodResolver` for any form beyond one input — the Zod schema is both the
validation and the TS type. `register` for native inputs, `Controller` only for custom
components. Errors are accessible: `aria-invalid`, `aria-describedby`, `role="alert"`. Server
rejections map back via `setError`; dynamic lists use `useFieldArray`; `reset()` after
successful submit.
Read **`refs/forms-and-validation.md`** when: building or reviewing a form, adding validation,
displaying field errors, handling server-side validation failures, or managing dynamic field
lists.

### 8. Security
React escapes JSX — never feed user content to `dangerouslySetInnerHTML` without DOMPurify
(allowlist tags). Sanitize user-supplied URLs before `href` (block `javascript:`);
`target="_blank"` pairs with `rel="noopener noreferrer"`. No secrets in the bundle —
`NEXT_PUBLIC_*`/`VITE_*` means public. Tokens live in HttpOnly cookies, not localStorage. Set
CSP headers server-side; `npm audit` gates CI.
Read **`refs/security-frontend.md`** when: rendering user-generated content, handling rich
text or URLs, configuring CSP, storing auth tokens, adding env vars, or reviewing for XSS.

### 9. Testing
Vitest + React Testing Library + userEvent + MSW. Query by role > label > text > testid —
tests resemble real usage, never component internals. `userEvent` over `fireEvent`; MSW mocks
the network (not the fetch client) so the real data path runs; `await screen.findBy*` for
async, never timeouts. axe assertions on interactive components.
Read **`refs/testing-frontend.md`** when: writing component or hook tests, setting up
Vitest/MSW, choosing queries, testing forms or async UI, or asserting accessibility.

### 10. Accessibility
Semantic HTML before ARIA: `<button>` for actions, `<a href>` for navigation, landmarks for
structure — never `<div onClick>`. Every input has a programmatic label (placeholder is not a
label). Dialogs trap focus, close on Escape, and return focus (use Radix/native `<dialog>`).
Dynamic messages need `aria-live`/`role="alert"`. Contrast ≥ 4.5:1; color is never the only
signal. jsx-a11y lints in CI.
Read **`refs/accessibility.md`** when: building interactive widgets, modals, or forms; adding
images or icons; announcing async results; styling focus states; or fixing an axe/jsx-a11y
finding.

### 11. Performance
Measure before optimizing: bundle analyzer and React Profiler first. Split code at routes and
heavy features (`React.lazy`/`dynamic`); many small Suspense boundaries beat one global one.
Keep input responsive with `useDeferredValue`/`useTransition`. `next/image` and `next/font`
(reserved space — CLS); lazy third-party scripts; virtualize lists past ~200 rows. Targets:
LCP < 2.5 s, CLS < 0.1, INP < 200 ms.
Read **`refs/performance-frontend.md`** when: a page or interaction is slow, adding heavy
dependencies, rendering long lists, optimizing images/fonts, or placing Suspense boundaries.

### 12. Styling
One approach per project: Tailwind (default for new Next.js apps) or CSS Modules — avoid
runtime CSS-in-JS (RSC-incompatible). No styling logic in inline `style`; toggle classes with
`clsx`/`cn`. Every color/spacing/radius comes from a design token (Tailwind theme or CSS
variables) — no magic numbers. Dark mode is CSS-driven (`data-theme` + tokens). Mobile-first
breakpoints.
Read **`refs/styling.md`** when: choosing a styling approach, writing conditional styles,
defining or using design tokens, implementing dark mode, or reviewing for magic values.

### 13. Next.js & SSR
Server Components by default; `'use client'` only on interactive leaves, pushed as deep as
possible. Fetch with explicit caching (`force-cache` / `revalidate` / `no-store`);
parallelize with `Promise.all`. Server Actions are public endpoints — Zod-validate and
authorize inside every action. TanStack Query hydrates via per-request `QueryClient` +
`HydrationBoundary` (never module-level on the server). `loading.tsx`/`error.tsx` per segment;
metadata via the Metadata API.
Read **`refs/nextjs-and-ssr.md`** when: writing pages/layouts, placing `'use client'`,
fetching in Server Components, adding Server Actions, configuring caching/revalidation, or
streaming with Suspense.

### 14. Build & CI
`tsc --noEmit` is a mandatory CI step — bundlers transpile without type-checking. Gate order:
typecheck → eslint → prettier → vitest → `npm audit` → build → Lighthouse CI (budgets for
performance ≥ 0.9, a11y ≥ 0.95). Path alias `@/ → src/` declared in tsconfig and mirrored in
the bundler. Bundle budgets fail CI on regression; named imports for tree shaking; `npm ci`
with a committed lockfile.
Read **`refs/build-and-ci.md`** when: setting up CI, configuring path aliases, enforcing
bundle budgets, wiring Lighthouse CI, validating env vars, or debugging prod-only build
issues.

### 15. Design cloning from a reference URL
When asked to clone or match a website's look and feel: **Acquire** (fetch the page HTML and
linked CSS — `:root` custom properties are the primary token source; ask for a screenshot if
the site is JS-rendered or blocked), **Distill** the findings into a reviewable
`DESIGN_SPEC.md` (tokens, layout anatomy, component inventory, character), then **Generate**
tokens-first code that passes this skill's own rules. Clone the design language only — never
logos, brand names, copyrighted images, or text; placeholder content always.
Read **`refs/design-cloning.md`** when: the user provides a reference URL or screenshot to
copy, says "make it look like …" or "clone the design of …", or asks to extract a site's
design tokens or theme.

### Pre-ship gate
Before calling React/TypeScript frontend code done, validate it against
**`tooling/style-checklist.md`** and ensure these three commands pass from the project root:

```bash
npx tsc --noEmit           # strict type checking, noUncheckedIndexedAccess, import type
npx eslint .               # hooks rules, jsx-a11y, no-explicit-any, floating promises
npx prettier --check .     # formatting
```

The checklist is the verifiable counterpart to the rules above — a failing item is a fix, not
a suggestion. Copy `tooling/eslint.config.js`, `tooling/prettier.config.js`, and
`tooling/tsconfig.base.json` into the target project as the starting configuration.
