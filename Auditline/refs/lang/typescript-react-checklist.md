# TypeScript/React checklist

Sources: React, Next.js and TanStack Query docs; WCAG 2.2; WAI-ARIA 1.2 and the ARIA Authoring
Practices Guide; WHATWG HTML Standard; TypeScript handbook; Zustand and React Hook Form docs;
MITRE CWE as cited per rule. Distilled from CodeWriter's TypeScript/React refs (see the
provenance comment on each section).

## Contents

1. How to use this checklist
2. Naming and layout
3. TypeScript strictness
4. React patterns
5. State management
6. Data fetching
7. API contracts
8. Forms and validation
9. Security
10. Testing
11. Accessibility
12. Performance
13. Styling
14. Next.js and SSR
15. Build and CI
16. Design cloning

## 1. How to use this checklist

- **Scope.** Load this file for `.tsx` and `.jsx` files, React hooks and components, and
  `tsconfig.json`, together with at most three topic refs. The topic refs own the rules shared by
  all languages (`refs/correctness.md` has the React rules `TS-COR-11` to `TS-COR-13`,
  `refs/performance.md` has `TS-PERF-09` and `TS-PERF-10`); this file names which apply to each
  area and adds what is specific to React, Next.js and the browser. Server-only TypeScript uses the
  Node checklist.
- **Tools first.** Run `tsc --noEmit` and `eslint` with `react-hooks` and `jsx-a11y` (project
  config first). Report their hits with `source: tsc|eslint`. Add a model finding only for what
  they cannot judge.
- **Rule IDs.** `TS-<CAT>-NN`. Numbers 01-49 are defined in the topic refs and are shared across
  languages; numbers from 51 up are defined in the language checklists, and the same number is the
  same concept in all of them. Accessibility rules are `TS-ACC-NN` and triage with correctness.
- **Accessibility levels.** Rate by the flow behind the control, as in X-SEV-06: minor on a
  secondary control, major when it is the only way through a core flow (checkout, login, submit,
  navigation, closing a dialog). WCAG Level A failures are not blockers by themselves.
- **Not flagged.** CodeWriter rules about how to write code (Zustand versus Jotai, CSS Modules
  versus Tailwind, feature co-location, `React.FC`, named exports, `interface` versus `type`,
  `staleTime` values, URL as state, Lighthouse budgets) are style or design choices. Report them
  only when the project states the convention and the diff breaks it. A missing CSP or security
  header the diff does not show is at most a question (X-SEV-09).

## 2. Naming and layout

<!-- provenance: CodeWriter/typescript/refs/naming-and-layout.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-MAINT-01` (unused imports), `TS-MAINT-02` (misleading names, boolean props),
barrel files with `export *` defeat tree shaking (`TS-PERF-10`).

### TS-COR-73 — Hook called conditionally, or a hook not named `use*`
- **Detect:** a hook (`useState`, `useEffect`, a custom `use*`) called inside an `if`, a loop, after
  an early `return`, in a nested function or after a `try`; a custom function that calls hooks but
  is not named `useSomething` (so the lint rule never checks its callers); a hook called from a
  class component or a plain function.
- **Default severity:** major (C2/R1: React throws "Rendered more hooks than during the previous
  render", or state attaches to the wrong hook).
- **Why:** React identifies hooks by call order; the order must be the same on every render.
- WRONG:
  ```tsx
  function Profile({ id }: { id?: string }) {
    if (!id) return null;
    const user = useUser(id);                     // skipped on some renders
    return <h1>{user.name}</h1>;
  }
  function getTheme() { return useContext(ThemeContext); }   // calls a hook, but is not named use*
  ```
- CORRECT:
  ```tsx
  function Profile({ id }: { id?: string }) {
    const user = useUser(id ?? '', { enabled: Boolean(id) });
    if (!id) return null;
    return <h1>{user.data?.name}</h1>;
  }
  function useTheme() { return useContext(ThemeContext); }
  ```
- **Fix:** call hooks unconditionally at the top level; rename wrappers to `use*`.
- **Cite:** React docs, "Rules of Hooks"; React docs, "Reusing Logic with Custom Hooks" (names
  starting with `use`).
- **Tool code:** `[eslint: react-hooks/rules-of-hooks]` (the tool owns the conditional-call case; the
  unnamed wrapper is a model finding).

## 3. TypeScript strictness

<!-- provenance: CodeWriter/typescript/refs/typescript-strict.md @ f07d926c79a25eee736da26c1fec88e89f94a8fe -->

Covered by: `TS-MAINT-08` (`any`, `as T`, `@ts-ignore`, `!`, `JSON.parse(...) as T`),
`TS-COR-04` (indexed access and `find` results without `noUncheckedIndexedAccess`).

### TS-MAINT-53 — Compiler or linter strictness weakened
- **Detect:** in `tsconfig*.json`: `"strict": false`, `"noImplicitAny": false`,
  `"strictNullChecks": false`, `"noUncheckedIndexedAccess": false`, `skipLibCheck` added to hide
  your own errors; in ESLint config: a `react-hooks` or `jsx-a11y` rule turned `off`; inline
  `// @ts-nocheck`, `// eslint-disable react-hooks/exhaustive-deps`.
- **Default severity:** minor; major when the change silences an error the diff itself introduces.
- **Why:** the safety net shrinks with no visible reason.
- WRONG:
  ```json
  { "compilerOptions": { "strict": true, "noUncheckedIndexedAccess": false } }
  ```
- CORRECT:
  ```json
  { "compilerOptions": { "strict": true, "noUncheckedIndexedAccess": true } }
  ```
- **Fix:** keep the flag on and fix the errors; scope a necessary exception to one file with the
  reason.
- **Cite:** TypeScript docs, "TSConfig Reference: strict"; typescript-eslint, `ban-ts-comment`.
- **Tool code:** `[typescript-eslint: ban-ts-comment]` for inline directives; none for config
  changes.

## 4. React patterns

<!-- provenance: CodeWriter/typescript/refs/react-patterns.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-COR-11` (stale closure, dependency array, `exhaustive-deps` disabled), `TS-COR-12`
(effect cleanup, out-of-order responses), `TS-COR-13` (derived state in an effect, index keys),
`TS-ERR-11` (error boundary, loading state in `finally`), `TS-PERF-09` (memoization, inline props).
Not flagged: function components versus classes and HOCs in code the diff does not write.

### TS-COR-72 — Number or string on the left of `&&` in JSX
- **Detect:** `{count && <Badge />}`, `{items.length && <List items={items} />}`,
  `{name && <Greeting />}` where the left side can be `0`, `NaN` or `''`.
- **Default severity:** minor (C3: the page shows a stray `0`); major when the screen is a price,
  quantity or status where a bare `0` is misread.
- **Why:** React renders `0` and `NaN`; only `false`, `null`, `undefined` and `''` render nothing.
- WRONG:
  ```tsx
  {cart.items.length && <CheckoutButton />}        // renders "0" for an empty cart
  ```
- CORRECT:
  ```tsx
  {cart.items.length > 0 && <CheckoutButton />}
  ```
- **Fix:** make the condition a boolean (`> 0`, `Boolean(x)`, `!!x`), or use a ternary.
- **Cite:** React docs, "Conditional Rendering" (do not put numbers on the left side of `&&`).
- **Tool code:** `[eslint: react/jsx-no-leaked-render]`.

### TS-COR-75 — Effect used to run the logic of a user action
- **Detect:** a `useEffect` whose body sends a POST, an analytics event, a notification or a
  toast in response to state set by a click or submit (`useEffect(() => { if (submitted) post(...) },
  [submitted])`).
- **Default severity:** major (C2/R1: the action runs twice in development Strict Mode and again
  whenever the component remounts, and it is detached from the event that caused it).
- **Why:** an effect describes synchronization with an external system, not a response to a click.
- WRONG:
  ```tsx
  useEffect(() => {
    if (submitted) api.createOrder(order);            // fires again on remount, twice in Strict Mode
  }, [submitted, order]);
  ```
- CORRECT:
  ```tsx
  function onSubmit() { createOrder.mutate(order); }  // in the handler, with useMutation
  ```
- **Fix:** put the logic in the event handler (or a mutation); keep effects for synchronization.
- **Cite:** React docs, "You Might Not Need an Effect" (sending a POST request on user action);
  React docs, "Synchronizing with Effects" (Strict Mode re-runs effects in development).
- **Tool code:** none.

## 5. State management

<!-- provenance: CodeWriter/typescript/refs/state-management.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-COR-13` (props or query data copied into `useState`), `TS-PERF-09` (context value
rebuilt every render). Not flagged: the choice of state library or URL-as-state.

### TS-COR-01 — Module-level mutable state shared across requests or users
- **Detect:** in code that runs on the server (a Next.js server component, route handler, layout,
  `getServerSideProps`, any file without `'use client'` that SSR renders): `const queryClient = new
  QueryClient()` or a Zustand `create(...)` store at module scope that holds user data; `let` or a
  plain object mutated by a component or loader. (A module-level `QueryClient` in a client-only
  module is correct.)
- **Default severity:** blocker when user-specific data can be served to another user (X-SEV-01:
  leaks across users, C1/R1); major for non-sensitive shared state. File the cross-user case as
  `TS-SEC-04` so a `--security-only` review keeps it; this rule is for state that is not about
  another user's data.
- **Why:** on the server one module instance serves every request, so state set for one user is
  visible to the next.
- WRONG:
  ```tsx
  // app/layout.tsx  (server)
  const queryClient = new QueryClient();                    // shared by every request
  export default async function Layout({ children }) {
    await queryClient.prefetchQuery({ queryKey: ['me'], queryFn: getCurrentUser });
    return <HydrationBoundary state={dehydrate(queryClient)}>{children}</HydrationBoundary>;
  }
  ```
- CORRECT:
  ```tsx
  export default async function Layout({ children }) {
    const queryClient = new QueryClient();                  // one per request
    await queryClient.prefetchQuery({ queryKey: ['me'], queryFn: getCurrentUser });
    return <HydrationBoundary state={dehydrate(queryClient)}>{children}</HydrationBoundary>;
  }
  ```
- **Fix:** create the client or store inside the request (or in a provider's `useState` on the
  client); never keep per-user data in module scope on the server.
- **Cite:** TanStack Query docs, "Advanced Server Rendering" (create the `QueryClient` per request
  to avoid sharing data between users); Zustand docs, "Setup with Next.js" (no global store on the
  server); CWE-488.
- **Tool code:** none.

### TS-PERF-56 — Whole-store or whole-form subscription
- **Detect:** `const store = useStore()` with no selector (Zustand); `const all = watch()` at the
  top of a React Hook Form component; a context holding many fields that most consumers read one of.
- **Default severity:** minor (C3: every change re-renders the component); major on a large form or
  list with typing lag.
- **Why:** the component re-renders when any field changes, not only the one it uses.
- WRONG:
  ```tsx
  const { user, cart, theme } = useStore();           // re-renders on any store change
  const values = watch();                              // re-renders the whole form on each keystroke
  ```
- CORRECT:
  ```tsx
  const userName = useStore((s) => s.user.name);
  const email = useWatch({ control, name: 'email' });   // subscribes in a small child component
  ```
- **Fix:** narrow selectors; `useWatch` in the child that needs the value.
- **Cite:** Zustand docs, "Selecting multiple state slices" and "Prevent rerenders"; React Hook Form
  docs, `watch` versus `useWatch` (performance).
- **Tool code:** none.

## 6. Data fetching

<!-- provenance: CodeWriter/typescript/refs/data-fetching.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-COR-16` (query key missing a variable; mutation without invalidation),
`TS-COR-11` and `TS-COR-12` (`useEffect` + `fetch`), `TS-ERR-04` and `TS-ERR-11` (status check,
error state), `TS-COR-02` (mutation retried or fired twice). Not flagged: `staleTime` values,
Suspense mode, and pagination style.

### TS-ERR-55 — Optimistic update without rollback or settle
- **Detect:** `useMutation` with `onMutate` that writes to the cache (`setQueryData`) and no
  `onError` that restores the snapshot, or no `onSettled` that invalidates; a manual optimistic
  state update with no revert path.
- **Default severity:** major (C2/R1: the UI keeps showing data the server rejected).
- **Why:** the screen is wrong until the next refetch, and the user believes the save worked.
- WRONG:
  ```tsx
  useMutation({
    mutationFn: updateTodo,
    onMutate: async (todo) => { queryClient.setQueryData(['todos'], (old) => replace(old, todo)); },
  });                                                    // a 500 leaves the edit on screen
  ```
- CORRECT:
  ```tsx
  useMutation({
    mutationFn: updateTodo,
    onMutate: async (todo) => {
      await queryClient.cancelQueries({ queryKey: ['todos'] });
      const previous = queryClient.getQueryData(['todos']);
      queryClient.setQueryData(['todos'], (old) => replace(old, todo));
      return { previous };
    },
    onError: (_err, _todo, ctx) => queryClient.setQueryData(['todos'], ctx?.previous),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['todos'] }),
  });
  ```
- **Fix:** snapshot in `onMutate`, restore in `onError`, invalidate in `onSettled`.
- **Cite:** TanStack Query docs, "Optimistic Updates".
- **Tool code:** none.

### TS-COR-76 — Query runs with a missing parameter
- **Detect:** `useQuery({ queryKey: ['user', id], queryFn: () => getUser(id!) })` where `id` can be
  `undefined` and there is no `enabled: Boolean(id)`; a request URL that becomes
  `/api/users/undefined`; a dependent query that does not wait for the first.
- **Default severity:** minor (C3: a wasted failing request); major when the request hits a
  different endpoint (`/api/users/` returns the list) or fails visibly on first render.
- **Why:** a query starts as soon as the component mounts, whether or not its inputs exist.
- WRONG:
  ```tsx
  const { data } = useQuery({ queryKey: ['user', userId], queryFn: () => getUser(userId!) });
  ```
- CORRECT:
  ```tsx
  const { data } = useQuery({
    queryKey: ['user', userId],
    queryFn: () => getUser(userId as string),
    enabled: Boolean(userId),
  });
  ```
- **Fix:** `enabled`, or `skipToken`; never call the hook conditionally.
- **Cite:** TanStack Query docs, "Dependent Queries" (the `enabled` option).
- **Tool code:** `[typescript-eslint: no-non-null-assertion]` for the `!`.

## 7. API contracts

<!-- provenance: CodeWriter/typescript/refs/api-contracts.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-MAINT-08` (`as Order` on a parsed response: assertion, not validation),
`TS-MAINT-04` (the same type or schema defined twice).

### TS-ERR-52 — `schema.parse()` of a network response outside error handling
- **Detect:** `OrderSchema.parse(await res.json())` in a component, hook or event handler with no
  `try`/`catch` and no error boundary above it; `parse` used where the failure should show a
  field error.
- **Default severity:** minor; major on a main flow (a schema mismatch becomes a blank screen).
- **Why:** `parse` throws a `ZodError`; `safeParse` returns a result the code must handle.
- WRONG:
  ```tsx
  const order = OrderSchema.parse(await res.json());      // a new API field type blanks the page
  ```
- CORRECT:
  ```tsx
  const parsed = OrderSchema.safeParse(await res.json());
  if (!parsed.success) throw new ApiContractError(parsed.error);   // handled by the query's error state
  const order = parsed.data;
  ```
- **Fix:** `safeParse` and a defined failure path, or `parse` inside the `queryFn` so the query's
  error state shows it.
- **Cite:** Zod docs, "Basic usage" (`parse` throws, `safeParse` returns a result).
- **Tool code:** none.

## 8. Forms and validation

<!-- provenance: CodeWriter/typescript/refs/forms-and-validation.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-ACC-02` (input without an accessible name; error text not linked to the field),
`TS-ERR-11` (submit error not shown), `TS-COR-02` (double submit), `TS-PERF-56` (`watch()`),
`TS-COR-13` (index keys in `useFieldArray`; use `field.id`). Not flagged: React Hook Form versus
`useState` per field.

## 9. Security

<!-- provenance: CodeWriter/typescript/refs/security-frontend.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-SEC-16` (`dangerouslySetInnerHTML`), `TS-SEC-26` (user URL in `href`/`src`),
`TS-SEC-02` (secret in client code, `NEXT_PUBLIC_*`/`VITE_*` holding a private value),
`TS-SEC-27` (token in `localStorage`), `TS-SEC-22` (deep merge of unvalidated objects, prototype
pollution), `TS-SEC-04` and `TS-SEC-20` (Server Actions without an ownership or auth check),
`X-SEC-01` (dependency changes). Not flagged: `target="_blank"` without `rel="noopener"`. HTML
treats `target="_blank"` as `noopener` by default in current browsers, so no finding unless the
project must support browsers that do not. A missing CSP is a question (X-SEV-09).

### TS-SEC-15 — Input evaluated as code in the browser
- **Detect:** `eval(...)`, `new Function(...)`, `setTimeout("code string", ms)`,
  `setInterval("...")`, `document.write(...)`, `script.textContent = value`, or
  `element.innerHTML = ...` with `<script>`-bearing data, where any part of the string comes from a
  URL, storage, an API response or user input.
- **Default severity:** blocker when untrusted input reaches the string (C1/R1, X-SEV-04 class);
  minor for a constant string.
- **Why:** it runs attacker text with the page's privileges.
- WRONG:
  ```tsx
  const fn = new Function('row', `return row.${params.get('field')}`);   // ?field=constructor.constructor(...)()
  setTimeout(`track('${eventName}')`, 0);
  ```
- CORRECT:
  ```tsx
  const field = params.get('field');
  const value = field && ALLOWED_FIELDS.has(field) ? row[field as keyof Row] : undefined;
  setTimeout(() => track(eventName), 0);
  ```
- **Fix:** no string-to-code APIs; look values up from an allowlist; pass a function to timers.
- **Cite:** CWE-95; OWASP A03:2021 Injection; MDN, `eval()` ("never use eval") and
  `setTimeout` (string argument).
- **Tool code:** `[eslint: no-eval, no-new-func, no-implied-eval]`.

## 10. Testing

<!-- provenance: CodeWriter/typescript/refs/testing-frontend.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-TEST-09` (queries by class or test id, `fireEvent`, un-awaited `userEvent`,
whole-tree snapshots), `TS-TEST-05` (sleeps; use `findBy*`), `TS-TEST-04` (mocking your own hooks
instead of the network), `TS-TEST-08` (shared `QueryClient`; mocks not reset), `TS-TEST-02`
(vacuous assertions). Not flagged: MSW versus other mocks, one behavior per test, `vitest-axe`
use.

## 11. Accessibility

<!-- provenance: CodeWriter/typescript/refs/accessibility.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Rate by the flow behind the control (section 1). Every rule cites a WCAG 2.2 success criterion and
the tool that backs it. A new interactive component with none of these problems needs no comment.

### TS-ACC-01 — Click handler on an element that is not interactive
- **Detect:** X-SEV-06 settles the level. `onClick` on `div`, `span`, `li` or `img` with no `role`,
  no `tabIndex` and no key handler; an `<a>` without `href` used as a button.
- **Default severity:** minor for one secondary control; major when it is the only way through a
  core flow (X-SEV-06).
- **Why:** keyboard and many screen-reader users cannot reach or activate it.
- WRONG:
  ```tsx
  <div className="filters__toggle" onClick={() => setOpen(!open)}>Filters</div>
  ```
- CORRECT:
  ```tsx
  <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>Filters</button>
  ```
- **Fix:** a native `<button>` or `<a href>`.
- **Cite:** WCAG 2.2 SC 2.1.1 Keyboard (A); WAI-ARIA APG, "Button pattern".
- **Tool code:** `[jsx-a11y: click-events-have-key-events, no-static-element-interactions, interactive-supports-focus]`.

### TS-ACC-02 — Form control without an accessible name or linked error
- **Detect:** `<input>`, `<select>` or `<textarea>` with no `<label htmlFor>`, `aria-label` or
  `aria-labelledby` (a `placeholder` is not a label); an error `<p>` that is not tied to the field
  (`aria-describedby`) and not announced (`role="alert"`); `aria-invalid` missing on an invalid
  field.
- **Default severity:** minor; major for the main field of a core form (login, checkout).
- **Why:** screen-reader users hear an unnamed edit field and never learn that it failed.
- WRONG:
  ```tsx
  <input type="email" placeholder="Email" value={email} onChange={onChange} />
  {error && <p className="error">{error}</p>}
  ```
- CORRECT:
  ```tsx
  <label htmlFor="email">Email</label>
  <input id="email" type="email" value={email} onChange={onChange}
         aria-invalid={Boolean(error)} aria-describedby={error ? 'email-error' : undefined} />
  {error && <p id="email-error" role="alert">{error}</p>}
  ```
- **Fix:** a visible `<label>`; link and announce the error.
- **Cite:** WCAG 2.2 SC 1.3.1 Info and Relationships (A), 3.3.1 Error Identification (A), 3.3.2
  Labels or Instructions (A), 4.1.2 Name, Role, Value (A).
- **Tool code:** `[jsx-a11y: label-has-associated-control, control-has-associated-label]`.

### TS-ACC-03 — Image without a text alternative
- **Detect:** `<img>` with no `alt`; a decorative image with a descriptive `alt` (screen readers
  read it); `alt="image"` or a file name; an icon-only button or link with no accessible name.
- **Default severity:** minor; major when the image is the only content of a link or control.
- **Why:** the content is invisible to screen readers.
- WRONG:
  ```tsx
  <img src="/chart.png" />
  <a href="/cart"><img src="/cart-icon.svg" alt="" /></a>      // link with no name
  ```
- CORRECT:
  ```tsx
  <img src="/chart.png" alt="Sales by month, rising from 12 to 40" />
  <a href="/cart"><img src="/cart-icon.svg" alt="Cart" /></a>
  ```
- **Fix:** meaningful `alt`; `alt=""` for decoration; an accessible name for icon controls.
- **Cite:** WCAG 2.2 SC 1.1.1 Non-text Content (A); W3C WAI, "Images tutorial".
- **Tool code:** `[jsx-a11y: alt-text, anchor-has-content]`.

### TS-ACC-04 — Dialog without focus management
- **Detect:** a custom modal (`role="dialog"` or a positioned `div`) that does not move focus in,
  does not trap Tab, does not close on Escape, or does not return focus to the trigger; no
  `aria-modal` or accessible name. (Radix, Headless UI and native `<dialog>` handle these.)
- **Default severity:** minor; major when the dialog is part of a core flow (confirm payment, sign
  in) or has no keyboard way to close it.
- **Why:** keyboard users are left behind the overlay or trapped in it.
- WRONG:
  ```tsx
  {open && <div className="modal"><button onClick={() => setOpen(false)}>Close</button></div>}
  ```
- CORRECT:
  ```tsx
  <Dialog.Root open={open} onOpenChange={setOpen}>      {/* Radix: focus trap, Escape, focus return */}
    <Dialog.Content><Dialog.Title>Confirm</Dialog.Title>…</Dialog.Content>
  </Dialog.Root>
  ```
- **Fix:** use a tested primitive; otherwise manage focus, Escape and `aria-modal` explicitly.
- **Cite:** WCAG 2.2 SC 2.1.2 No Keyboard Trap (A), 2.4.3 Focus Order (A); WAI-ARIA APG, "Dialog
  (Modal) Pattern".
- **Tool code:** none.

### TS-ACC-05 — Focus indicator removed
- **Detect:** `outline: none`, `outline: 0` or Tailwind `outline-none` / `focus:outline-none` on
  an interactive element with no replacement style (`:focus-visible` ring, box-shadow, border).
- **Default severity:** minor.
- **Why:** keyboard users cannot see where they are.
- WRONG:
  ```css
  button:focus { outline: none; }
  ```
- CORRECT:
  ```css
  button:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; }
  ```
- **Fix:** style `:focus-visible`; never remove the outline without a replacement.
- **Cite:** WCAG 2.2 SC 2.4.7 Focus Visible (AA) and 2.4.13 Focus Appearance.
- **Tool code:** none.

### TS-ACC-06 — Status or error message not announced
- **Detect:** a toast, inline error, loading or "saved" message inserted into the DOM with no
  live region (`role="status"`, `role="alert"`, `aria-live`), or a live region created together
  with its message (it must exist before the message).
- **Default severity:** minor.
- **Why:** screen-reader users get no feedback that something happened.
- WRONG:
  ```tsx
  {saved && <div className="toast">Saved</div>}
  ```
- CORRECT:
  ```tsx
  <div role="status" aria-live="polite">{saved ? 'Saved' : ''}</div>     {/* always mounted */}
  ```
- **Fix:** a live region that is mounted before the message appears.
- **Cite:** WCAG 2.2 SC 4.1.3 Status Messages (AA); WAI-ARIA APG, "Alert pattern".
- **Tool code:** none.

### TS-ACC-07 — Contrast below the threshold, or colour as the only signal
- **Detect:** literal text and background colours in the diff whose contrast ratio is below 4.5:1
  (3:1 for large text and UI components); an error state shown only by a red border or text colour;
  a link distinguished only by colour.
- **Default severity:** minor; no finding for a ratio you did not compute.
- **Why:** low-vision and colour-blind users cannot read or perceive it.
- WRONG:
  ```css
  .hint { color: #999; background: #fff; }          /* 2.85:1 */
  ```
- CORRECT:
  ```css
  .hint { color: #595959; background: #fff; }       /* 7:1 */
  ```
- **Fix:** darker colour or token; add an icon or text to colour-coded states.
- **Cite:** WCAG 2.2 SC 1.4.3 Contrast (Minimum) (AA), 1.4.1 Use of Color (A), 1.4.11 Non-text
  Contrast (AA).
- **Tool code:** none (compute the ratio per the WCAG relative-luminance formula).

### TS-ACC-08 — Positive `tabIndex` or keyboard trap
- **Detect:** `tabIndex={1}` or any value above 0; `tabIndex={-1}` on an element users must reach;
  a key handler that calls `preventDefault` on Tab.
- **Default severity:** minor.
- **Why:** a positive value pulls the element out of the natural order and makes tab order
  unpredictable.
- WRONG:
  ```tsx
  <input tabIndex={3} />
  ```
- CORRECT:
  ```tsx
  <input />                                          {/* DOM order is the tab order */}
  ```
- **Fix:** use `0` or `-1` only, and fix the DOM order instead.
- **Cite:** WCAG 2.2 SC 2.4.3 Focus Order (A); WAI-ARIA APG, "Developing a Keyboard Interface".
- **Tool code:** `[jsx-a11y: tabindex-no-positive, no-noninteractive-tabindex]`.

### TS-ACC-09 — ARIA misuse
- **Detect:** `role="button"` on a `div` without keyboard handling; a `role` without its required
  attributes (`role="checkbox"` without `aria-checked`); `aria-hidden="true"` on a focusable
  element or an ancestor of one; `aria-label` on a `span` or `div` with no role (naming is
  prohibited on generic elements); an invalid ARIA attribute or role; redundant roles
  (`<button role="button">`).
- **Default severity:** minor.
- **Why:** wrong ARIA is worse than none: it announces behavior the element does not have.
- WRONG:
  ```tsx
  <span aria-label="Close">×</span>
  <button aria-hidden="true" onClick={close}>Close</button>
  ```
- CORRECT:
  ```tsx
  <button type="button" aria-label="Close" onClick={close}>×</button>
  ```
- **Fix:** native elements first; ARIA only for what HTML cannot express.
- **Cite:** WAI-ARIA 1.2 (naming prohibited on `generic`); WAI-ARIA APG, "No ARIA is better than
  bad ARIA"; WCAG 2.2 SC 4.1.2 Name, Role, Value (A).
- **Tool code:** `[jsx-a11y: aria-props, aria-role, role-has-required-aria-props, no-aria-hidden-on-focusable]`.

## 12. Performance

<!-- provenance: CodeWriter/typescript/refs/performance-frontend.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-PERF-09` (re-renders, unbounded list rendered row by row), `TS-PERF-10` (import
cost, route-level code splitting, `'use client'` too high), `TS-PERF-01` (request waterfall).
Not flagged: Core Web Vitals targets, `useTransition`, Suspense boundary placement.

### TS-PERF-52 — Layout-shifting or render-blocking assets
- **Detect:** `<img>` without `width` and `height` (or an aspect-ratio box) on the first screen;
  `next/image` replaced with raw `<img>` for large images; `priority` on many images; a synchronous
  third-party `<script src>` in `<head>`; web fonts with no `font-display`.
- **Default severity:** minor (C3: layout shift and slower first paint).
- **Why:** the browser cannot reserve space or must wait for the asset.
- WRONG:
  ```tsx
  <img src="/hero.jpg" alt="Product" />
  <script src="https://cdn.example.com/widget.js" />
  ```
- CORRECT:
  ```tsx
  <Image src="/hero.jpg" alt="Product" width={1200} height={600} priority />
  <Script src="https://cdn.example.com/widget.js" strategy="lazyOnload" />
  ```
- **Fix:** sized images, `loading="lazy"` below the fold, `next/script` strategies, `font-display:
  swap`.
- **Cite:** web.dev, "Optimize Cumulative Layout Shift" and "Efficiently load third-party
  JavaScript"; Next.js docs, "Image" and "Script".
- **Tool code:** `[eslint: @next/next/no-img-element, @next/next/no-sync-scripts]` with the Next.js
  ESLint plugin.

## 13. Styling

<!-- provenance: CodeWriter/typescript/refs/styling.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Not flagged: the choice between Tailwind and CSS Modules, dark-mode mechanism, breakpoints,
responsive approach and class naming.

### TS-MAINT-60 — Hard-coded design value where the project has tokens
- **Detect:** only when the project defines tokens (CSS variables, a Tailwind theme, a
  `tokens.ts`): raw hex colours, pixel spacing or font sizes in components; Tailwind arbitrary
  values (`bg-[#3b82f6]`, `p-[13px]`); inline `style={{ color: '#333' }}` for static values.
- **Default severity:** nit; minor when the same literal appears three or more times.
- **Why:** a theme or brand change has to find every copy.
- WRONG:
  ```tsx
  <button style={{ background: '#3b82f6', padding: '13px 17px' }}>Save</button>
  ```
- CORRECT:
  ```tsx
  <button className="bg-primary px-4 py-3">Save</button>
  ```
- **Fix:** use the token; add one if the value is genuinely new.
- **Cite:** Tailwind docs, "Theme configuration"; W3C Design Tokens Community Group, "Design Tokens
  Format Module".
- **Tool code:** none (`[eslint: tailwindcss/no-arbitrary-value]` when configured).

## 14. Next.js and SSR

<!-- provenance: CodeWriter/typescript/refs/nextjs-and-ssr.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Covered by: `TS-COR-01` (per-request state), `TS-SEC-04` / `TS-SEC-20` (Server Actions), `TS-COR-16`
(a write that never calls `revalidatePath` / `revalidateTag`), `TS-ERR-11` (no `error.tsx`),
`TS-PERF-10` (`'use client'` on a large tree). Not flagged: metadata API versus `<title>`, cache
mode defaults, `loading.tsx` use.

### TS-COR-74 — Server-only module reachable from client code
- **Detect:** a file that reads non-public environment variables, a database client, `fs`, or
  secrets, and is imported (directly or through a barrel) by a file marked `'use client'`; a module
  that holds server secrets without `import 'server-only'`.
- **Default severity:** major (C2/R1: the value is `undefined` in the browser and the feature
  fails, or the module and its dependencies are bundled into client JavaScript). Blocker when the
  file contains a secret literal (`TS-SEC-02`).
- **Why:** a client component's imports are part of the browser bundle, and only `NEXT_PUBLIC_*`
  variables exist there.
- WRONG:
  ```tsx
  // lib/db.ts
  export const db = new Client({ connectionString: process.env.DATABASE_URL });
  // components/Cart.tsx
  'use client';
  import { db } from '@/lib/db';                     // the database client in the browser bundle
  ```
- CORRECT:
  ```tsx
  // lib/db.ts
  import 'server-only';                              // build error if a client module imports it
  export const db = new Client({ connectionString: process.env.DATABASE_URL });
  ```
- **Fix:** add `import 'server-only'` to server modules; pass data to client components as props;
  call a Server Action or API route from the client.
- **Cite:** Next.js docs, "Server and Client Components: Keeping server-only code out of the client
  environment" (the `server-only` package).
- **Tool code:** none.

### TS-COR-77 — Client environment variable read dynamically
- **Detect:** `process.env[name]` or `const { NEXT_PUBLIC_X } = process.env` in code that runs in
  the browser; destructuring or bracket access of `NEXT_PUBLIC_*` variables.
- **Default severity:** major (C2/R1: the value is `undefined` in the production bundle and works
  in development).
- **Why:** Next.js replaces the literal expression `process.env.NEXT_PUBLIC_X` at build time; any
  other access is not replaced.
- WRONG:
  ```tsx
  const key = 'NEXT_PUBLIC_ANALYTICS_ID';
  setupAnalytics(process.env[key]);                  // undefined in the browser
  ```
- CORRECT:
  ```tsx
  setupAnalytics(process.env.NEXT_PUBLIC_ANALYTICS_ID);
  ```
- **Fix:** reference each variable by its full literal name; validate once in a module.
- **Cite:** Next.js docs, "Environment Variables: Bundling Environment Variables for the Browser"
  (dynamic lookups are not inlined).
- **Tool code:** none.

## 15. Build and CI

<!-- provenance: CodeWriter/typescript/refs/build-and-ci.md @ f07d926c79a25eee736da26c1fec88e89f94a8fe -->

Covered by: `TS-TEST-06` (CI step removed, `continue-on-error`, `|| true`), `X-DIFF-04` (lockfile
and `npm ci`), `TS-PERF-10` (bundle size), `TS-SEC-02` (client env var holding a secret),
`TS-MAINT-53` (`exclude`/`strict` changes in `tsconfig`). Not flagged: CI gate order, Lighthouse
budgets, source-map hosting.

### TS-COR-78 — Path alias declared in one place only
- **Detect:** the diff adds or changes `compilerOptions.paths` (`"@/*": ["src/*"]`) without the
  matching alias in the bundler (`vite.config` `resolve.alias`, webpack, `next.config`) or the test
  runner (`vitest` / `jest` `moduleNameMapper`), or code imports `@/…` in a package run directly by
  Node.
- **Default severity:** major (C2/R1: `tsc` passes, then the build, the tests or `node` fail with
  "Cannot find module").
- **Why:** `paths` only teaches the type checker; it does not rewrite imports.
- WRONG:
  ```json
  { "compilerOptions": { "paths": { "@/*": ["./src/*"] } } }
  ```
  ```ts
  // vite.config.ts: no resolve.alias for "@"  →  "Failed to resolve import @/lib/api"
  ```
- CORRECT:
  ```ts
  // vite.config.ts
  export default defineConfig({ resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } } });
  ```
- **Fix:** mirror the alias in every tool that resolves imports (bundler, test runner, linter
  resolver), or use a plugin that reads `tsconfig.json`.
- **Cite:** TypeScript handbook, "Modules - Reference: `paths`" (`paths` does not change emitted
  specifiers); Vite docs, `resolve.alias`.
- **Tool code:** none.

## 16. Design cloning

<!-- provenance: CodeWriter/typescript/refs/design-cloning.md @ ef073a0caec63238da443370319ecc90956f9764 -->

Applies when the change reproduces the look of a reference site. Hard-coded colours and spacing
copied from the reference are `TS-MAINT-60`; a clone must also pass every section above.

### TS-MAINT-61 — Cloned design carries the source's brand
- **Detect:** logos, product or company names, trademarked slogans, copied marketing text or
  copyrighted images from the reference site in the diff (asset names such as `acme-logo.svg`,
  copy that matches the reference page, a footer "© Other Company").
- **Default severity:** minor; major when it is user-visible copy or a logo in a shipped build
  (legal exposure, not a code defect). Medium confidence; this is a flag for the owner, not legal
  advice.
- **Why:** a layout and a colour palette can be reproduced; another party's brand and text cannot.
- WRONG:
  ```tsx
  <header><img src="/stripe-logo.svg" alt="Stripe" /><h1>Financial infrastructure to grow your revenue</h1></header>
  ```
- CORRECT:
  ```tsx
  <header><img src="/placeholder-logo.svg" alt="Your product" /><h1>Placeholder headline</h1></header>
  ```
- **Fix:** neutral placeholders for logos, names and copy; substitute open fonts for commercial
  ones.
- **Cite:** 17 U.S.C. §102(b) (copyright protects expression, not ideas or systems);
  USPTO, "Trademark basics".
- **Tool code:** none.
