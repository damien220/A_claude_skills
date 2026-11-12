# Auditline report

**Scope:** file, 5 files: `module_a.tsx`, `module_b.tsx`, `module_c.tsx`, `module_e.test.tsx`, `module_e.tsx` · **Mode:** full · **Languages:** typescript
**Tools:** eslint: ran (bundled fallback config) · tsc: ran (project tsconfig.json)
**Tool results triaged out (17 eslint, 8 tsc, with reasons):** eslint `n/no-unsupported-features/node-builtins` for `Response` in the test (no Node engine range in this bundle); eslint `no-unsafe-assignment` on `await db.*` and `await getSession()` in module_e.tsx (21, 22, 33-36, 44, 45: `@/lib/db` and `@/lib/auth` do not resolve here, so the values are `any`); eslint `no-unused-vars` on the `s` parameter of a function type in module_e.tsx:89 (a type-only name, not a binding); eslint `react/jsx-no-leaked-render` on boolean operands in module_a.tsx:104, module_b.tsx:175, module_e.tsx:126, module_e.tsx:157 (`isError`/`searchFailed` are booleans); eslint `react/jsx-no-leaked-render` on `review.author &&` in module_a.tsx:109 (an object or undefined, cannot render a number); eslint `no-unnecessary-condition` on `translation.variables?.reviewId` in module_a.tsx:126 (`variables` is undefined before the first mutate); eslint `react/no-array-index-key` on static placeholders in module_e.tsx:149 (no state in them); tsc TS2307 for `@/lib/db`, `@/lib/auth`, `@/lib/logger` (module_e.tsx:5-7, module_e.test.tsx:5) and TS2339 for `toBeInTheDocument` (module_e.test.tsx:45-47, 68): path aliases and jest-dom types are not configured in this bundle.
**Coverage:** all 5 files reviewed (file scope; nothing is pre-existing).

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 14 | 8 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.tsx:25` TS-SEC-02: Translation API key hardcoded in a module that runs in the browser

```tsx
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';
```

**Why:** The key is a literal in source, and line 32 sends it as a Bearer token from `translate()`, which the browser runs. Every visitor can read it from the bundle, and git keeps it after deletion, so anyone can use the provider account. Any visitor who loads a product page reaches it (R1). Not downgraded: X-SEV-04 class.
**Fix:** Call the provider from an own route handler that reads `process.env.TRANSLATE_API_KEY` on the server and fails fast when unset; rotate the key that is now public.
**Cite:** CWE-798; CWE-200 (secret in client bundle); OWASP A07:2021 Identification and Authentication Failures
**Source:** model · confidence: high

### [blocker] `module_c.tsx:101` TS-SEC-16: Review text rendered as HTML with dangerouslySetInnerHTML

```tsx
dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
```

**Why:** `review.body` is written by customers, and the translated text comes from a third-party service. Both reach innerHTML on every product page, so a review containing a script runs in each visitor's session (stored XSS, R1). eslint react/no-danger reported it; the consequence on this path is blocker.
**Fix:** Render as text: `{translated[review.id] ?? review.body}`. If HTML is required, sanitize with DOMPurify first.
**Cite:** CWE-79; OWASP A03:2021 Injection; React docs, dangerouslySetInnerHTML
**Source:** eslint (`react/no-danger`) · confidence: high

### [blocker] `module_e.tsx:44` TS-SEC-04: deleteTask server action deletes a task with no session or membership check

```tsx
const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
```

**Why:** `deleteTask` is a `'use server'` function, which is a public POST endpoint. It deletes the row named by the client and only then reads `projectId` for revalidation. It never calls `requireProjectMember`, which `updateTaskStatus` calls at line 34. Any signed-up user who has a task UUID (they leak in URLs and shared links) can delete any project's task (R1).
**Fix:** Read the task's project first, call `requireProjectMember(projectId)`, and delete only after it passes, as `updateTaskStatus` does: `const { projectId } = await db.task.findUniqueOrThrow({ where: { id }, select: { projectId: true } }); await requireProjectMember(projectId);`
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; Next.js docs, Data Security (Server Actions are public endpoints)
**Source:** model · confidence: high

### [blocker] `module_e.tsx:49` TS-SEC-04: Module-level QueryClient on the server shares one request's task data with the next request

```tsx
const serverQueryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
```

**Why:** `ProjectBoardPage` prefetches into this client and dehydrates all of it. The server keeps one module instance for every request, so the tasks prefetched for one project by one member are included in the HTML of the next request, for any user and any project. Cross-user data exposure on a normal page load (R1); filed under the security rule so a security-only review keeps it.
**Fix:** Create the client inside `ProjectBoardPage` (one `new QueryClient(...)` per request) and prefetch into that instance.
**Cite:** CWE-488; CWE-200; TanStack Query docs, Advanced Server Rendering (create the QueryClient per request)
**Source:** model · confidence: high

### [major] `module_c.tsx:51` TS-ERR-11: Reviews load has no status check and the loading state is never cleared on failure

```tsx
const res = await fetch(`/api/products/${productId}/reviews`);
```

**Why:** `setLoading(true)` runs before this fetch, and `setLoading(false)` runs only at the end of `load()`. A network error, a non-2xx response (there is no `res.ok` check) or a body that is not JSON throws, so the spinner stays on forever and no error is shown. On the product-reviews main flow this is C2 x R1, so major.
**Fix:** Wrap the body in try/catch/finally, check `res.ok` before `res.json()`, and render an error state with `role="alert"`. TanStack Query (as module_a uses) gives `isError` for free.
**Cite:** CWE-755; React docs, Catching rendering errors with an error boundary (boundaries do not catch async errors); WCAG 2.2 SC 4.1.3
**Source:** model · confidence: high

### [major] `module_c.tsx:55` TS-PERF-01: One request per review author in a sequential loop

```tsx
const authorRes = await fetch(`/api/users/${review.authorId}`);
```

**Why:** Each review adds an awaited round trip before the list renders, so a product with 200 reviews waits for 200 requests in a row on every page load. The count grows with reviews the user does not control (X-SEV-02: major). The tool reported lines 55 and 56 (no-await-in-loop); they are one defect and are merged here.
**Fix:** Fetch the authors once with `/api/users?ids=...` as module_a's `fetchReviews` does, or have the reviews endpoint return authors.
**Cite:** CWE-1073; web.dev, Avoid chaining critical requests
**Source:** eslint (`no-await-in-loop`) · confidence: high

### [major] `module_c.tsx:63` TS-COR-10: load() is called without handling its rejection

```tsx
load();
```

**Why:** eslint no-floating-promises: the promise from `load()` is dropped. When `res.json()` or an author fetch throws (see line 51), the rejection is unhandled and the component keeps its loading state. The caller assumes the work finished, so major under COR-10.
**Fix:** `load().catch((err) => setError(err))`, or move the fetch into a query and read its error state.
**Cite:** typescript-eslint, no-floating-promises; MDN, Using promises (unhandled rejections)
**Source:** eslint (`@typescript-eslint/no-floating-promises`) · confidence: high

### [major] `module_c.tsx:64` TS-COR-11: Effect omits productId, so a changed product keeps the previous product's reviews

```tsx
}, []);
```

**Why:** eslint react-hooks/exhaustive-deps: `productId` is read by `load()` (line 51) but is not in the list. When the product prop changes, the effect does not run again, and the page keeps showing reviews of the previous product (visible wrong data, C2 x R1).
**Fix:** List `[productId]` and keep `load` inside the effect; ignore responses that arrive after cleanup (abort or an ignore flag).
**Cite:** React docs, Synchronizing with Effects; React docs, Removing Effect Dependencies
**Source:** eslint (`react-hooks/exhaustive-deps`) · confidence: high

### [major] `module_c.tsx:69` TS-COR-16: Translation stored under review id only, so a changed target language shows the old translation

```tsx
setTranslated((prev) => ({ ...prev, [review.id]: text }));
```

**Why:** The translation is keyed by `review.id` alone, and line 101 reads it under the same key whatever `targetLanguage` is. If the language prop changes while the component stays mounted, every review shows a translation into the previous language (wrong locale served, C2 x R1). Assumption: the language prop can change without a remount; module_a keys by review and target and does not have this problem.
**Fix:** Key by both, for example `${review.id}:${targetLanguage}`, and read the same key on line 101.
**Cite:** TanStack Query docs, Query Keys (every input the result depends on belongs in the key)
**Source:** model · confidence: medium

### [major] `module_e.test.tsx:10` TS-TEST-07: Membership mock always grants access, so no test proves a non-member is rejected

```tsx
membership: { findUnique: vi.fn(async () => ({ role: 'member' })) },
```

**Why:** The factory returns a membership for every lookup, and no test overrides it to return null. Deleting the `!membership` check in module_e.tsx (line 23) leaves every test green. New authorization logic with no test of the denial is major under TEST-07.
**Fix:** Add a test that makes `findUnique` resolve to `null` and asserts that the action rejects and the row is unchanged.
**Cite:** refs/tests.md TEST-07 (mock factory that always grants); OWASP Authorization Cheat Sheet
**Source:** model · confidence: high

### [major] `module_e.test.tsx:43` TS-TEST-06: it.only narrows the whole file to one test

```tsx
it.only('renders one column per status', async () => {
```

**Why:** The other three tests in this file (cards, search, move) are skipped when this runs, so the suite stays green while checking less of TaskBoard. Vitest fails a CI run that contains `.only` (allowOnly defaults to !CI), so this is blocked in CI and only narrows local runs; the defect is the same either way.
**Fix:** Remove `.only`.
**Cite:** Vitest docs, test.only and allowOnly; refs/tests.md TEST-06
**Source:** model · confidence: high

### [major] `module_e.test.tsx:67` TS-COR-10: user.type is not awaited, so the no-error assertion runs before any typing

```tsx
user.type(search, 'login');
```

**Why:** eslint no-floating-promises. The assertion on line 68 runs before the keystrokes, so the test passes whether or not an error appears while typing. It is the only test of that behavior, so it gives false confidence (TEST-02, major).
**Fix:** `await user.type(search, 'login');` and then assert the absence of the alert after the typing has finished.
**Cite:** Testing Library, user-event docs (await the user-event calls); typescript-eslint, no-floating-promises
**Source:** eslint (`@typescript-eslint/no-floating-promises`) · confidence: high

### [major] `module_e.test.tsx:76` TS-TEST-02: Move test asserts that a mock is defined, not that the task changed status

```tsx
expect(db.task.update).toBeDefined();
```

**Why:** `toBeDefined()` passes for any mock. The test does not check that the card moved or that the update wrote `status: 'done'`, and it is the only test of the move behavior (TEST-02, major). The mocked `findUniqueOrThrow` returns undefined, so the real server action throws in this test; no assertion would notice.
**Fix:** Mock `findUniqueOrThrow` to return `{ projectId }`, then assert `db.task.update` was called with `{ where: { id }, data: { status: 'done' } }` and that the card is in the Done column.
**Cite:** refs/tests.md TEST-02; Testing Library, Guiding Principles
**Source:** model · confidence: high

### [major] `module_e.tsx:20` TS-TEST-01: Project membership check has no test

```tsx
async function requireProjectMember(projectId: string) {
```

**Why:** This is the authorization gate for `updateTaskStatus`, and `deleteTask` should call it too. The only test file mocks the gate to always grant, and it drives TaskBoard in the browser. No test calls the server actions or the membership check, so a deleted or inverted check passes the suite. Auth logic with no test is major (TEST-01).
**Fix:** Add server-side tests for `updateTaskStatus` and `deleteTask`: a non-member is rejected and the row is unchanged.
**Cite:** OWASP Authorization Cheat Sheet; CWE-862
**Source:** model · confidence: high

### [major] `module_e.tsx:85` TS-COR-11: UpdatedAgo timer keeps the first updatedAt, so the label stays wrong when the task changes

```tsx
}, []);
```

**Why:** eslint react-hooks/exhaustive-deps: `updatedAt` is read in the interval callback (line 83) and is missing from the list. The board keys cards by index (line 167), so a card can receive another task's `updatedAt` and keep the first task's age until it remounts (visible wrong data, C2 x R1).
**Fix:** List `[updatedAt]` as the dependency, or compute the label from `updatedAt` during render with a `now` state.
**Cite:** React docs, Removing Effect Dependencies; React docs, Synchronizing with Effects
**Source:** eslint (`react-hooks/exhaustive-deps`) · confidence: high

### [major] `module_e.tsx:118` TS-COR-12: Search effect has no cancellation, so an older slow response can overwrite newer results

```tsx
getTasks(projectId, term)
```

**Why:** Every keystroke runs the effect and starts a request with no abort and no ignore flag. A slow response for an earlier term that arrives after a later one sets `results` to the stale list, so the results shown do not match the search box (visible wrong result, C2 x R1). The effect also has no cleanup.
**Fix:** Pass an AbortSignal and abort in the cleanup, or set an `ignore` flag in the cleanup and set results only when it is not set.
**Cite:** React docs, Synchronizing with Effects (fetching data, cleanup); MDN, AbortController
**Source:** model · confidence: high

### [major] `module_e.tsx:140` TS-ERR-55: Move update has no rollback, so a failed save leaves the card in the new column

```tsx
queryClient.setQueryData<Task[]>(tasksKey, (prev) => prev?.map((t) => (t.id === taskId ? { ...t, status } : t)));
```

**Why:** `onMutate` writes the new status into the cache, and there is no `onError` to restore a snapshot. When `updateTaskStatus` fails, `onSuccess` does not run, so the cache keeps the new status and the card stays in the wrong column until the next refetch. The banner says the change was not saved while the board shows it as saved (C2 x R1).
**Fix:** Snapshot in `onMutate` (`cancelQueries`, then `getQueryData`), restore the snapshot in `onError`, and invalidate in `onSettled` rather than `onSuccess`.
**Cite:** TanStack Query docs, Optimistic Updates
**Source:** model · confidence: high

### [major] `module_e.tsx:167` TS-COR-13: Task cards keyed by array index, so card state moves to the wrong task

```tsx
key={index}
```

**Why:** TaskCard keeps `confirmingDelete` in local state. Keyed by index, when a task leaves or moves within a column the next task inherits the open 'Confirm delete' state of the removed one, so a click can confirm deleting a different task from the one shown (wrong row edited, C2 x R1). The tool rated it minor from the lint rule alone.
**Fix:** `key={task.id}`.
**Cite:** React docs, Rendering Lists (keys)
**Source:** eslint (`react/no-array-index-key`) · confidence: high

### [minor] `module_a.tsx:89` TS-COR-10: Refetch promise discarded in the error-state retry button

```tsx
<button type="button" onClick={() => reviewsQuery.refetch()}>
```

**Why:** eslint no-misused-promises: `refetch()` returns a promise that the click handler drops. The outcome is already shown by the query's `isError` state, so no failure is lost and the caller does not assume the work is done. Minor under COR-10 (tool severity lowered from major).
**Fix:** Leave as is, or write `onClick={() => void reviewsQuery.refetch()}` to mark the discard.
**Cite:** typescript-eslint, no-misused-promises (checksVoidReturn); React docs, Responding to Events
**Source:** eslint (`@typescript-eslint/no-misused-promises`) · confidence: high

### [minor] `module_b.tsx:118` TS-COR-10: Refetch promise discarded in the invoice error-state retry button

```tsx
results = <p role="alert">Invoices could not be loaded. <button type="button" onClick={() => invoicesQuery.refetch()}>Try again</button></p>;
```

**Why:** eslint no-misused-promises. The same pattern as module_a: the failure is already in the query's error state, so nothing is lost. Minor under COR-10 (tool severity lowered from major).
**Fix:** Leave as is, or mark the discard with `void`.
**Cite:** typescript-eslint, no-misused-promises (checksVoidReturn); React docs, Responding to Events
**Source:** eslint (`@typescript-eslint/no-misused-promises`) · confidence: high

### [minor] `module_c.tsx:52` TS-MAINT-08: Network JSON cast to a type without validation

```tsx
const list = (await res.json()) as Review[];
```

**Why:** The cast trusts the shape of the reviews response. If a field is renamed or missing, `review.author.avatarUrl` (line 90) throws during render and the reviews section goes blank. An assertion is not a check (minor here; module_a parses the same response with zod).
**Fix:** Parse with a schema inside the fetch function: `z.array(reviewSchema).parse(await res.json())`, and handle the failure as in the line 51 finding.
**Cite:** Zod docs, Basic usage (parse throws, safeParse returns a result); TypeScript handbook, Type assertions
**Source:** model · confidence: high

### [minor] `module_c.tsx:59` TS-DIFF-01: console.log left in a load path that runs on every product page

```tsx
console.log('reviews loaded', withAuthors);
```

**Why:** eslint no-console. The browser console gets the customer display names and avatar URLs on every product page load. Minor, not a secret leak (X-SEV-07: minor on a request path or page-load code); the tool rated it nit.
**Fix:** Delete it, or use the project logger at debug level.
**Cite:** CWE-532; OWASP Logging Cheat Sheet
**Source:** eslint (`no-console`) · confidence: high

### [minor] `module_c.tsx:103` TS-ACC-01: Translate control is a clickable div, not reachable from the keyboard

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** A clickable div with no role, tabIndex or key handler. Keyboard and screen-reader users cannot reach or activate Translate. It is one secondary control (X-SEV-06: minor). The tool's COR-10 finding on this line is a separate defect and is reported above it.
**Fix:** `<button type="button" className="review__translate" onClick={() => handleTranslate(review)}>Translate</button>`
**Cite:** WCAG 2.2 SC 2.1.1 Keyboard (Level A); WAI-ARIA APG, Button pattern
**Source:** model · confidence: high

### [minor] `module_c.tsx:103` TS-COR-10: Translate handler promise dropped by the click handler

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** eslint no-misused-promises. `handleTranslate` catches every error (lines 70-72), so the dropped promise cannot lose a failure; minor under COR-10 (tool severity lowered from major).
**Fix:** `onClick={() => void handleTranslate(review)}` if the element stays a div; the button fix in TS-ACC-01 removes the question.
**Cite:** typescript-eslint, no-misused-promises (checksVoidReturn)
**Source:** eslint (`@typescript-eslint/no-misused-promises`) · confidence: high

### [minor] `module_e.test.tsx:53` TS-TEST-09: Test counts cards by class name instead of by what the user sees

```tsx
expect(container.querySelectorAll('.task-card')).toHaveLength(2);
```

**Why:** A class selector on the container breaks on a rename that changes nothing for users, and it does not check that the titles are visible. Minor (C3).
**Fix:** Query by role or text, for example `screen.getByRole('heading', ...)` for each title, or `findAllByRole('listitem')` inside each column.
**Cite:** Testing Library, About Queries (priority: getByRole first); refs/tests.md TEST-09
**Source:** model · confidence: high

### [minor] `module_e.tsx:163` TS-COR-72: Empty column shows a stray 0 under its heading

```tsx
{columnTasks.length && (
```

**Why:** eslint react/jsx-no-leaked-render. When a column has no tasks, `columnTasks.length` is `0`, which React renders as text. A bare 0 shows under the heading (C3: a stray value, no data error).
**Fix:** `{columnTasks.length > 0 && (`
**Cite:** React docs, Conditional Rendering (do not put numbers on the left side of &&)
**Source:** eslint (`react/jsx-no-leaked-render`) · confidence: high

### [nit] 2 nits from eslint (TS-MAINT-01)

Collapsed because eslint reports them: unused imports `useMemo` (`module_c.tsx:1`) and `useCallback` (`module_e.tsx:1`). Run `eslint --fix` or remove the names.

## Questions

Low-confidence blockers or majors, and absence-of-control items, go here, not above. Questions do not change the verdict.

- `module_e.tsx:132` — TaskBoard, TaskSearch and UpdatedAgo use React hooks, and this module imports the database client at line 6 with no 'use client' directive. If the file is an App Router server module, the hooks fail at build time. If the board is split into a client module, `@/lib/db` comes into the browser bundle with it. Which module boundary does the real project use for this file?

## Pre-existing (not part of this change)

None: file scope, so nothing is pre-existing.

