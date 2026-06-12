# TypeScript Frontend Style Checklist

This is the pre-ship gate. Before declaring any React/TypeScript frontend code done, validate
every section that applies to the change. A failing item is a fix, not a suggestion.

Run `npx tsc --noEmit && npx eslint . && npx prettier --check .` before opening a PR.

---

## Naming & File Layout → `refs/naming-and-layout.md`

- [ ] Components `PascalCase`; exported component name matches the filename
- [ ] Custom hooks named `use*` — the prefix is required for `rules-of-hooks` linting
- [ ] Utilities `camelCase.ts` (pure, no JSX); directories `kebab-case/`
- [ ] Boolean props read as predicates (`isLoading`, `hasError`, `disabled`)
- [ ] Handler functions `handle*`; handler props `on*`
- [ ] Constants `UPPER_SNAKE_CASE`; grouped constants are `as const` objects
- [ ] `interface` for props shapes; `type` for unions and aliases; no `I` prefix
- [ ] Feature co-location: component + hook + types + tests + styles in one feature directory
- [ ] Barrel `index.ts` exports an explicit public API — no `export *`
- [ ] Next.js reserved filenames (`page`, `layout`, `loading`, `error`, `route`) used only for their framework role

---

## TypeScript Strict → `refs/typescript-strict.md`

- [ ] `"strict": true`, `noUncheckedIndexedAccess`, `verbatimModuleSyntax`; no flag weakened without a comment
- [ ] No `any` in non-test code; `unknown` at boundaries (fetch JSON, `catch (err: unknown)`)
- [ ] Props typed with an explicit `interface Props`; no `React.FC`
- [ ] `children: React.ReactNode` (not `ReactElement` unless a single element is required)
- [ ] Events typed by element (`React.ChangeEvent<HTMLInputElement>`) — never `any`
- [ ] `useRef<HTMLElement>(null)` with explicit generic; `useState<T | null>(null)` where inference fails
- [ ] Generic components for typed collections — no `any[]`
- [ ] Indexed access handles `undefined` (empty states rendered, not crashed)
- [ ] `import type` for type-only imports; `satisfies` preferred over `as`
- [ ] `tsc --noEmit` passes with zero errors

---

## React Patterns → `refs/react-patterns.md`

- [ ] Functional components with named exports; no class components, no new HOCs
- [ ] No `useEffect` for derived state — derived values computed during render
- [ ] No `useEffect` for event logic — logic lives in the handler
- [ ] Every remaining `useEffect` synchronizes with an external system and has cleanup where needed
- [ ] No `eslint-disable` on `exhaustive-deps` — restructure instead
- [ ] `useMemo`/`useCallback`/`React.memo` only for referential stability or measured expense
- [ ] List keys come from data identity; index keys only for static lists
- [ ] No `{count && <El />}` rendering a literal `0` — boolean conditions forced
- [ ] Error boundaries (react-error-boundary or `error.tsx`) around async subtrees with retry fallback
- [ ] Components split when they juggle multiple distinct data concerns

---

## State Management → `refs/state-management.md`

- [ ] State classified: server → TanStack Query; local UI → `useState`/`useReducer`; shared client → Zustand/Jotai; filters/sort/pagination → URL
- [ ] Server data never copied into `useState` or a client store
- [ ] Props never mirrored into state (keyed remount or direct read instead)
- [ ] Multi-transition local state modeled as a typed `useReducer`
- [ ] Zustand consumed through narrow selectors — no whole-store subscriptions
- [ ] Context limited to low-frequency values; provider value memoized; consumer hook throws outside provider
- [ ] No module-level mutable state (`let` mutated by components)

---

## Data Fetching → `refs/data-fetching.md`

- [ ] No `useEffect` + `fetch` in new code — `useQuery`/`useSuspenseQuery` instead
- [ ] `queryKey` contains every parameter the queryFn depends on; key factories per feature
- [ ] `staleTime` set deliberately (app default + per-query overrides)
- [ ] Mutations via `useMutation`; `onSuccess` invalidates related queries; errors surfaced to the user
- [ ] Optimistic updates implement all three: `onMutate` (snapshot), `onError` (rollback), `onSettled` (invalidate)
- [ ] Dependent queries gated with `enabled`, never conditional hook calls
- [ ] Query errors handled at component level AND reported globally (QueryCache `onError`)
- [ ] Infinite/paginated lists use cursor-based `useInfiniteQuery` or `keepPreviousData`

---

## API Contracts → `refs/api-contracts.md`

- [ ] Every network response validated with Zod before touching state — no `as MyType` casts
- [ ] Types derived from schemas (`z.infer`) — never hand-written twice
- [ ] `safeParse` where failure is handled; `parse` only at trusted internal boundaries
- [ ] Centralized `apiFetch(path, schema)` wrapper; no raw `fetch` + raw JSON in components
- [ ] API error bodies validated against the Problem Details schema; one `humanize()` for user-facing copy
- [ ] Monorepos: schemas defined once and shared (shared package or tRPC) — no duplicated definitions

---

## Forms & Validation → `refs/forms-and-validation.md`

- [ ] React Hook Form + `zodResolver` for any form beyond a single input
- [ ] One Zod schema = validation + TS type for the form
- [ ] `register` for native inputs; `Controller` only for custom/third-party components
- [ ] Errors accessible: `aria-invalid`, `aria-describedby` → error element, `role="alert"`
- [ ] `<form noValidate>` with `handleSubmit` guarding submission
- [ ] Server-side rejections mapped back with `setError` (field-level when possible)
- [ ] `watch()` scoped (`useWatch` in a child) — no whole-form subscriptions
- [ ] Dynamic lists use `useFieldArray` with `field.id` keys
- [ ] `reset()` after successful submit; fetched entities bound via `values`/`defaultValues`

---

## Security → `refs/security-frontend.md`

- [ ] No `dangerouslySetInnerHTML` on user content without DOMPurify + tag allowlist
- [ ] User-supplied URLs protocol-checked before `href`/`src` (no `javascript:`)
- [ ] `target="_blank"` always with `rel="noopener noreferrer"`
- [ ] No secrets in client code — nothing named SECRET/PRIVATE/TOKEN behind `NEXT_PUBLIC_*`/`VITE_*`
- [ ] Auth tokens in HttpOnly cookies — never localStorage/sessionStorage
- [ ] CSP + security headers set server-side (`next.config.js` headers or middleware)
- [ ] No `eval`/`new Function`/string timers; no deep-merge of unvalidated user objects
- [ ] `npm audit --audit-level=high` passes; lockfile committed; `npm ci` in CI

---

## Testing → `refs/testing-frontend.md`

- [ ] Vitest + RTL + userEvent + MSW; `jsdom` environment
- [ ] Queries by role > label > text > testid; no `container.querySelector`
- [ ] `userEvent.setup()` for interactions — `fireEvent` only with a justifying comment
- [ ] Network mocked with MSW (`onUnhandledRequest: 'error'`); per-test overrides via `server.use`
- [ ] Async waits use `findBy*`/`waitForElementToBeRemoved` — no sleeps
- [ ] One behavior per `it()`; AAA shape; loading/error/empty/data states all covered
- [ ] Fresh QueryClient per test with `retry: false`; mocks and handlers reset between tests
- [ ] axe (`vitest-axe`) assertion on interactive components
- [ ] No snapshot tests of whole component trees; no implementation-detail assertions

---

## Accessibility → `refs/accessibility.md`

- [ ] Native elements for interaction: `<button>`/`<a href>` — no `<div onClick>`
- [ ] Landmarks (`header`/`nav`/`main`/`footer`) structure the page; ARIA only where HTML has no equivalent
- [ ] Dialogs trap focus, close on Escape, return focus to trigger (Radix/native `<dialog>`)
- [ ] All interactive elements keyboard-reachable and operable; no positive `tabIndex`
- [ ] Focus visible — no `outline: none` without replacement
- [ ] Every input labeled (`<label htmlFor>` or `aria-label`); placeholder is not a label
- [ ] Informative images have descriptive `alt`; decorative images `alt=""`
- [ ] Dynamic status messages in `aria-live`/`role="alert"` regions that pre-exist the message
- [ ] Contrast ≥ 4.5:1 (3:1 large text/UI); color never the only signal
- [ ] `eslint-plugin-jsx-a11y` passes; new UI keyboard-walked manually

---

## Performance → `refs/performance-frontend.md`

- [ ] Measured before optimized: bundle analyzer / React Profiler evidence for any optimization
- [ ] Routes and heavy features code-split (`React.lazy` / `next/dynamic`)
- [ ] Multiple co-located Suspense boundaries; skeletons sized like content (CLS)
- [ ] Expensive filtered renders use `useDeferredValue`/`useTransition`
- [ ] Images via `next/image` (or sized `<img loading="lazy">`); `priority` only on the LCP image
- [ ] Fonts via `next/font` (or preloaded WOFF2 + `font-display: swap`)
- [ ] Third-party scripts deferred (`next/script` `lazyOnload`) — never sync in `<head>`
- [ ] Named imports for tree shaking; heavy deps checked on bundlephobia before adoption
- [ ] Lists past ~200 rows virtualized (TanStack Virtual)
- [ ] Core Web Vitals within targets: LCP < 2.5 s, CLS < 0.1, INP < 200 ms

---

## Styling → `refs/styling.md`

- [ ] One approach per project (Tailwind or CSS Modules); no runtime CSS-in-JS in new code
- [ ] No styling logic in inline `style` — conditional classes via `clsx`/`cn`
- [ ] Inline styles only for truly dynamic values, piped through CSS variables
- [ ] All colors/spacing/radii/shadows from design tokens — no magic numbers
- [ ] Dark mode via tokens + `data-theme`/`prefers-color-scheme` (no FOUC)
- [ ] `globals.css` holds only reset + tokens + base typography; no global tag styling
- [ ] Mobile-first `min-width` breakpoints from tokens; container queries for slot-adaptive components
- [ ] CSS Modules co-located with their component; camelCase class names

---

## Next.js & SSR → `refs/nextjs-and-ssr.md`

- [ ] Server Components by default; `'use client'` pushed to the smallest interactive leaves
- [ ] No hooks/browser APIs in Server Components; server→client props serializable
- [ ] RSC data fetched with explicit cache mode; independent requests parallelized (`Promise.all`)
- [ ] Server Actions Zod-validate input AND check authorization inside the action
- [ ] Mutations revalidate (`revalidateTag`/`revalidatePath`) after writes
- [ ] TanStack Query SSR: per-request QueryClient + `HydrationBoundary` — never module-level on the server
- [ ] `loading.tsx`/`error.tsx` per segment; slow subtrees streamed with `<Suspense>`
- [ ] Metadata via `export const metadata`/`generateMetadata` — no `<title>` in JSX

---

## Build & CI → `refs/build-and-ci.md`

- [ ] `tsc --noEmit` runs in CI (bundlers don't type-check)
- [ ] Gate order: typecheck → eslint → prettier → vitest → audit → build → Lighthouse
- [ ] Path alias `@/ → src/` in tsconfig AND mirrored in the bundler/test runner
- [ ] Bundle size budget enforced (size-limit / First Load JS tracked); regressions fail CI
- [ ] Client env vars statically referenced and Zod-validated; `.env` gitignored, `.env.example` committed
- [ ] Lighthouse CI budgets: performance ≥ 0.9, accessibility ≥ 0.95, on a production build
- [ ] Production build inspected: no accidentally-dynamic routes; source maps to the error tracker, not the public

---

## Design Cloning → `refs/design-cloning.md`

- [ ] Only the design language cloned — no logos, brand names, copyrighted images, or copied text
- [ ] `DESIGN_SPEC.md` written with token table + evidence, layout anatomy, component inventory
- [ ] Spec confirmed with the user before bulk generation (unless one-shot was requested)
- [ ] Commercial fonts substituted with the nearest open alternative via `next/font`
- [ ] Extracted values land as design tokens — zero inline hex/px copied from the reference
- [ ] Placeholder content everywhere; image slots use neutral placeholders
- [ ] Generated code passes this entire checklist (a clone is not a style-rule exception)
- [ ] Unrecoverable aspects (animations, imagery style) listed as open questions, not invented silently
