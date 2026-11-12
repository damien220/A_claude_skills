# Auditline report

**Scope:** file (5 files: module_a.tsx, module_b.tsx, module_c.tsx, module_e.tsx, module_e.test.tsx) · **Mode:** full · **Languages:** typescript
**Tools:** eslint: ran (bundled fallback config) · tsc: ran (project tsconfig.json)
**Coverage:** all 5 files in scope, reviewed per file.

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 10 | 9 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.tsx:25` TS-SEC-02: Live translation API key hardcoded in a client component

```tsx
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';
```

**Why:** The key has a `tr_live_` prefix, so it is a live credential. This component runs in the browser (it uses useState and useEffect and is rendered client-side), so the key is in the bundle that every visitor downloads and in git history. Anyone can read it and spend the account's quota or call the provider as the site. Reachability R1 (every visitor), consequence C1 (credential exposed). X-SEV-04: not downgraded.
**Fix:** Remove the key from the client. Call a server route that holds the key, as `translateReview` in module_a.tsx does (`/api/reviews/:id/translate`). Rotate the leaked key now and read any server key from an environment variable.
**Cite:** CWE-798; CWE-200 (secret exposed in client bundle); OWASP A07:2021 Identification and Authentication Failures
**Source:** model · confidence: high

### [blocker] `module_c.tsx:101` TS-SEC-16: User-controlled text rendered as HTML (dangerouslySetInnerHTML)

```tsx
dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
```

**Why:** The HTML comes from the review body (written by any customer) or from the translation response (third-party output). A review containing an `<img onerror=...>` tag runs script on every visitor's page in the site origin: stored XSS (X-SEV-04, not downgraded). Translation output is also untrusted: the provider can return markup.
**Fix:** Render the text as a child: `<div className="review__body">{translated[review.id] ?? review.body}</div>`. Sanitize with DOMPurify only where HTML is genuinely required.
**Cite:** CWE-79; OWASP A03:2021 Injection; React docs, "dangerouslySetInnerHTML"
**Source:** eslint (`react/no-danger`) · confidence: high

### [blocker] `module_e.tsx:44` TS-SEC-04: deleteTask server action deletes a task with no session or membership check

```tsx
const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
```

**Why:** `deleteTask` is a `'use server'` function, so it is a public POST endpoint. It takes a task id and deletes the row with no `getSession()` or `requireProjectMember()` call. `updateTaskStatus` (lines 33-34) does both; this one does neither. Any caller who has or obtains a task UUID, including an anonymous one, deletes the task. The project id is used only to revalidate the path afterwards. Reachability R1, consequence C1 (data loss by any caller).
**Fix:** Look up the task's project first, then call `await requireProjectMember(projectId)` before the delete, as `updateTaskStatus` does. Add a role check if deletion needs one.
**Cite:** CWE-862 (missing authorization); CWE-639; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [blocker] `module_e.tsx:59` TS-SEC-04: Shared server QueryClient dehydrates other requests' tasks into every page

```tsx
<HydrationBoundary state={dehydrate(serverQueryClient)}>
```

**Why:** `serverQueryClient` (line 49) is created at module scope, so one instance serves every request on the server. `prefetchQuery` writes each project's tasks into it, and `dehydrate(serverQueryClient)` serializes the whole cache into the HTML sent to the requester. A member of project A therefore receives the tasks of project B whenever another request prefetched B within the default gcTime. The membership check guards only the requester's own project. Filed as TS-SEC-04 per TS-COR-01 (cross-user data). Reachability R1 (any signed-in user), consequence C1 (other tenants' data).
**Fix:** Create the QueryClient inside `ProjectBoardPage` so that each request has its own, and dehydrate only that client.
**Cite:** CWE-668 (exposure of resource to wrong sphere); CWE-488; TanStack Query docs, "Advanced Server Rendering"
**Source:** model · confidence: high

### [major] `module_c.tsx:55` TS-PERF-01: One author request per review, awaited in sequence on page load

```tsx
const authorRes = await fetch(`/api/users/${review.authorId}`);
```

**Why:** The loop awaits `/api/users/:id` once per review, one after another, on every page load. The number of reviews grows with a product's popularity, which is user-controlled growth (X-SEV-02: major on a request path over data that grows). The tool reported minor; raised for that reason. The `await authorRes.json()` on line 56 is the same defect and is merged here.
**Fix:** Fetch the distinct author ids in one batch request (`/api/users?ids=...`, as module_a.tsx does) so the page makes a single author call.
**Cite:** CWE-1073; web.dev, "Avoid chaining critical requests"
**Source:** eslint (`no-await-in-loop`) · confidence: high

### [major] `module_c.tsx:63` TS-COR-10: load() called without a catch: a failed fetch leaves the spinner on forever

```tsx
load();
```

**Why:** `load()` is fire-and-forget. Any rejection (a network error, a JSON error body on line 52 or 56 that is not the expected shape, or a missing `res.ok` check on lines 51-52) rejects with no handler. `setLoading(false)` never runs, so the user sees "Loading reviews..." indefinitely and the console shows an unhandled rejection. Reachability R1 (any visitor on a bad response), consequence C2 on the main screen. This also covers TS-ERR-11 and TS-ERR-04 for this function, so it is one finding.
**Fix:** `useEffect(() => { load().catch(() => setFailed(true)); }, [productId]);` with `setLoading(false)` in a `finally`, a `res.ok` check before parsing, and an error state in the render.
**Cite:** React docs, "Synchronizing with Effects" (fetching data in an effect); MDN, "Promise" (unhandled rejection)
**Source:** eslint (`@typescript-eslint/no-floating-promises`) · confidence: high

### [major] `module_c.tsx:64` TS-COR-11: Effect omits productId: reviews stay stale after the product changes

```tsx
}, []);
```

**Why:** The effect fetches `/api/products/${productId}/reviews` but its dependency array is `[]`. When the prop changes, the previous product's reviews stay on screen. A slower earlier response can also overwrite a newer one, because the effect has no ignore flag or abort (TS-COR-12). C2 on the main screen, R1.
**Fix:** Use `[productId]` as the dependency array and set an `ignore` flag in the effect with cleanup (`return () => { ignore = true; }`), or pass an AbortSignal to fetch.
**Cite:** React docs, "Removing Effect Dependencies"; React docs, "Synchronizing with Effects"
**Source:** eslint (`react-hooks/exhaustive-deps`) · confidence: high

### [major] `module_c.tsx:69` TS-COR-16: Translation cache keyed by review id only, ignoring the target language

```tsx
setTranslated((prev) => ({ ...prev, [review.id]: text }));
```

**Why:** `translated` is keyed by `review.id` here and on line 101, not by review and target language as module_a.tsx does with `translationKey`. After the `targetLanguage` prop changes, a review translated earlier still shows its old-language text, because the render looks up by id alone. This is a wrong result on a common screen under a specific condition (C2), reachable by any user who switches language after translating (R1), so major.
**Fix:** Key by both: `[`${review.id}:${targetLanguage}`]: text` (as `translationKey` in module_a.tsx), or clear the map when `targetLanguage` changes.
**Cite:** React docs, "Preserving and Resetting State" (state must follow the inputs it was computed from)
**Source:** model · confidence: high

### [major] `module_e.test.tsx:43` TS-TEST-06: it.only narrows the suite to one test

```tsx
it.only('renders one column per status', async () => {
```

**Why:** `it.only` makes the runner skip the other three tests in this file (lines 50, 56, 63 and 71), including the search and move tests. The run reports green while checking one case. Vitest rejects `.only` when CI is set and the project's config is not in scope here, so this is rated major per TS-TEST-06; it is minor only if CI rejects it.
**Fix:** Remove `.only`.
**Cite:** Vitest docs, "test.only" (allowOnly)
**Source:** model · confidence: high

### [major] `module_e.test.tsx:67` TS-COR-10: user.type is not awaited: the assertion runs before the typing happens

```tsx
user.type(search, 'login');
```

**Why:** `user.type` returns a promise that is not awaited, so the assertion on line 68 runs before any character is typed. `not.toBeInTheDocument` then passes whatever the component does, so the test cannot fail (TS-TEST-02, vacuous). It is the only test of the search error path, so major.
**Fix:** `await user.type(search, 'login');`
**Cite:** Testing Library, user-event docs, "Introduction" (await the calls)
**Source:** eslint (`@typescript-eslint/no-floating-promises`) · confidence: high

### [major] `module_e.test.tsx:76` TS-TEST-02: Move test asserts that a mock exists, not that the task moved

```tsx
expect(db.task.update).toBeDefined();
```

**Why:** `expect(db.task.update).toBeDefined()` is true for any `vi.fn()` mock, so the test passes whether or not the move happens. It selects a status and never checks the board afterwards. It is the only test of the move path, so major (false confidence).
**Fix:** After the select, `await screen.findByRole('heading', { name: 'Done (1)' })`, and optionally assert the update call arguments with `toHaveBeenCalledWith`.
**Cite:** Testing Library docs, "Guiding Principles" (assert what the user sees)
**Source:** model · confidence: high

### [major] `module_e.tsx:118` TS-COR-12: Search response for an older term can overwrite the results for a newer one

```tsx
getTasks(projectId, term)
```

**Why:** The effect fires a fetch on every keystroke, with no abort and no ignore flag. Responses can arrive out of order, so the results for 'log' can replace those for 'login' while the box shows 'login'. The list then shows matches for a term that is not in the box. Wrong visible result (C2) for any user who types (R1), so major.
**Fix:** Return an ignore flag from the effect (`let ignore = false; ... return () => { ignore = true; };`) and only call `setResults` when `!ignore`, or pass an AbortSignal to `getTasks`.
**Cite:** React docs, "Synchronizing with Effects" (cleanup and race conditions)
**Source:** model · confidence: high

### [major] `module_e.tsx:140` TS-ERR-55: Optimistic status move has no rollback: a failed save leaves the card in the new column

```tsx
queryClient.setQueryData<Task[]>(tasksKey, (prev) => prev?.map((t) => (t.id === taskId ? { ...t, status } : t)));
```

**Why:** `onMutate` writes the new status into the cache, but there is no `onError` to restore a snapshot. `onSuccess` invalidates only on success, so after a failed `updateTaskStatus` the board keeps showing the task in the new column while the alert says "Your last change was not saved." Consequence C2 on every failed move, reachability R1.
**Fix:** Snapshot the list in `onMutate` (`queryClient.getQueryData`), restore it in `onError`, and invalidate in `onSettled`.
**Cite:** TanStack Query docs, "Optimistic Updates"
**Source:** model · confidence: high

### [major] `module_e.tsx:167` TS-COR-13: Index used as the key for task cards that hold local state

```tsx
key={index}
```

**Why:** `TaskCard` keeps `confirmingDelete` in local state, and the key is the array index. When a task leaves or enters a column, the card in that slot keeps the previous card's state. A user who clicks Delete on one task can then see "Confirm delete" on a different task that moved into the same slot, and confirming deletes the wrong task. Wrong row acted on (C2), reachable on ordinary use (R1). Raised from the tool's minor.
**Fix:** `key={task.id}`.
**Cite:** React docs, "Rendering Lists" (keys)
**Source:** eslint (`react/no-array-index-key`) · confidence: high

### [minor] `module_a.tsx:89` TS-COR-10: Refetch promise passed straight to onClick

```tsx
<button type="button" onClick={() => reviewsQuery.refetch()}>
```

**Why:** refetch() resolves with the query result and does not reject unless throwOnError is set, so no rejection escapes this handler. The tool reported major; lowered to minor for that reason. The promise is still not awaited, which the fix makes explicit.
**Fix:** `onClick={() => { void reviewsQuery.refetch(); }}` states the intent; no other change needed.
**Cite:** TanStack Query docs, "refetch" (throwOnError); Python docs, "Coroutines and Tasks" (analogous rule)
**Source:** eslint (`@typescript-eslint/no-misused-promises`) · confidence: high

### [minor] `module_b.tsx:118` TS-COR-10: Refetch promise passed straight to onClick in the invoices error state

```tsx
results = <p role="alert">Invoices could not be loaded. <button type="button" onClick={() => invoicesQuery.refetch()}>Try again</button></p>;
```

**Why:** Same as module_a.tsx:89: refetch() resolves and does not reject by default, so no unhandled rejection can occur here. Lowered from the tool's major to minor.
**Fix:** `onClick={() => { void invoicesQuery.refetch(); }}` states the intent.
**Cite:** TanStack Query docs, "refetch" (throwOnError); MDN, "Promise" (unhandled rejection)
**Source:** eslint (`@typescript-eslint/no-misused-promises`) · confidence: high

### [minor] `module_c.tsx:59` TS-DIFF-01: console.log of reviews with author records left in the component

```tsx
console.log('reviews loaded', withAuthors);
```

**Why:** The log runs on every page load and prints the review and author objects (display names, avatar URLs). Only the visitor's own console shows it, so the exposure is limited. It is debug output on a request path (X-SEV-07 minor). Raised from the tool's nit because it runs on every load.
**Fix:** Delete the line.
**Cite:** CWE-532 (information written to log files); OWASP Logging Cheat Sheet
**Source:** eslint (`no-console`) · confidence: high

### [minor] `module_c.tsx:103` TS-COR-10: Async handler on a div: the promise is not awaited by the element

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** `handleTranslate` catches its own errors, so no rejection escapes. The lint is about the handler shape rather than a consequence, so the tool's major is lowered to minor. The real defect on this line is that the control is not an interactive element; that is reported separately as TS-ACC-01.
**Fix:** Use a native button (see the TS-ACC-01 finding); the promise-in-attribute warning goes away with it.
**Cite:** MDN, "Promise" (unhandled rejection); WAI-ARIA APG, "Button pattern"
**Source:** eslint (`@typescript-eslint/no-misused-promises`) · confidence: high

### [minor] `module_c.tsx:103` TS-ACC-01: Translate action is a div with onClick: not reachable by keyboard

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** The `div` has no role, no tabIndex and no key handler, so keyboard and screen-reader users cannot activate Translate. It is one secondary control, not the only path through a core flow, so minor (X-SEV-06 m4).
**Fix:** `<button type="button" className="review__translate" onClick={() => handleTranslate(review)}>Translate</button>`
**Cite:** WCAG 2.2 SC 2.1.1 Keyboard (Level A); WAI-ARIA APG, "Button pattern"
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:35` TS-TEST-04: fetch mock returns every task for every URL, so the search filter is never exercised

```tsx
vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify(TASKS), { status: 200 }));
```

**Why:** The mock returns both tasks whatever `q` is, so the assertion on line 60 (two matches for 'release') holds even if the server ignores the term or the component stops sending it. The search path is over-mocked: the test checks the mock, not the filter. Minor, because the test is not wrong today.
**Fix:** Make the mock filter by the `q` parameter of the request URL, and assert that the request carried `q=release`.
**Cite:** Vitest docs, "Mocking" (vi.spyOn)
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:53` TS-TEST-09: Counts cards with a class selector instead of a role or text query

```tsx
expect(container.querySelectorAll('.task-card')).toHaveLength(2);
```

**Why:** `container.querySelectorAll('.task-card')` couples the test to markup; renaming the class fails the test with no user-visible change. Minor (C3).
**Fix:** Query the cards by their titles, e.g. `expect(screen.getByRole('heading', { name: 'Write release notes' })).toBeInTheDocument()` and the same for the second task.
**Cite:** Testing Library docs, "About Queries" (priority: getByRole first)
**Source:** model · confidence: high

### [minor] `module_e.tsx:85` TS-COR-11: UpdatedAgo interval reads a stale updatedAt

```tsx
}, []);
```

**Why:** The interval closure is created once with `[]`, so `updatedAt` is frozen at mount. When the task's `updatedAt` changes, the label keeps the old age until the card remounts. The consequence is a display-only stale timestamp (C3, R1), so minor; the tool reported major.
**Fix:** Use `[updatedAt]` as the dependency array, or derive the label in render from `updatedAt` and a `now` state.
**Cite:** React docs, "Synchronizing with Effects"
**Source:** eslint (`react-hooks/exhaustive-deps`) · confidence: high

### [minor] `module_e.tsx:163` TS-COR-72: Empty column renders a stray 0

```tsx
{columnTasks.length && (
```

**Why:** `columnTasks.length && (` renders the number 0 inside the column when it is empty. This is a real leak, not a false positive. Cosmetic on the main screen (C3).
**Fix:** `{columnTasks.length > 0 && (`
**Cite:** React docs, "Conditional Rendering" (do not put numbers on the left of &&)
**Source:** eslint (`react/jsx-no-leaked-render`) · confidence: high

### Linter nits (collapsed)

2 nits from eslint (`no-unused-vars`): `module_c.tsx:1` (useMemo); `module_e.tsx:1` (useCallback). Run `eslint --fix` or remove the imports.

## Questions

Low-confidence blockers or majors, and absence-of-control items, go here, not above. Questions do not change the verdict.

- `module_e.tsx:6` — `db` (and `getSession` on line 5) come from modules with no server-only marker, and TaskBoard (hooks, no 'use client') sits in the same file. If any client component imports this file, the database client enters the browser bundle (TS-COR-74); if it is only server-rendered, TaskBoard's hooks fail. Is this file imported from a 'use client' module, and does lib/db import 'server-only'?
- `module_e.tsx:5` — The '@/lib/*' imports (lines 5-7; also module_e.test.tsx line 5) are not mapped in tsconfig.json (tsc TS2307). If the project maps them in another config, ignore this; otherwise the build fails.
- `module_e.test.tsx:45` — tsconfig.json sets "types": [], so the jest-dom matchers (toBeInTheDocument, lines 45-47 and 68) are untyped (tsc TS2339). If the jest-dom setup file is not part of the project, this test file will not type-check.

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
