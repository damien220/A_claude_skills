# Auditline report

**Scope:** file `module_a.tsx`, `module_b.tsx`, `module_c.tsx`, `module_e.tsx`, `module_e.test.tsx` (no git context) · **Mode:** full · **Languages:** typescript
**Tools:** eslint: ran (bundled fallback config) | tsc: ran (project tsconfig.json; dependency type declarations not installed, resulting errors discarded)
**Coverage:** all files in scope

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 10 | 8 | 4 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.tsx:25` TS-SEC-02: Live translation API key hardcoded in a client component

```tsx
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';
```

**Why:** The `tr_live_` key is sent as a Bearer credential from browser code (line 32), so it ships in the JS bundle to every visitor and sits in git history. Anyone can copy it and bill or abuse the translation account. Consequence C1 (secret exposed), reachability irrelevant: the leak happens at commit (X-SEV-04, never downgraded).
**Fix:** Move the call behind an own API route (e.g. POST /api/reviews/:id/translate) that reads the key from a server-side env var; rotate the leaked key.
**Cite:** CWE-798; CWE-200; OWASP A07:2021 Identification and Authentication Failures; OWASP Secrets Management Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_c.tsx:101` TS-SEC-16: Customer-written review body and third-party translation rendered as raw HTML

```tsx
dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
```

**Why:** `review.body` is text other users wrote and `translated[...]` is third-party API output; both go into `dangerouslySetInnerHTML`. A review containing `<img src=x onerror=...>` runs script in every visitor's session on the product page (stored XSS, C1/R1, X-SEV-04).
**Fix:** Render as text: `<p className="review__body">{translated[review.id] ?? review.body}</p>`; if HTML is truly needed, `DOMPurify.sanitize(...)` the value first.
**Cite:** CWE-79; OWASP A03:2021 Injection; React docs, `dangerouslySetInnerHTML`
**Source:** eslint (react/no-danger) · confidence: high

### [blocker] `module_e.tsx:41` TS-SEC-04: deleteTask Server Action deletes any task by id with no session or membership check

```tsx
export async function deleteTask(taskId: string): Promise<void> {
  'use server';
  const id = z.string().uuid().parse(taskId);
  const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
```

**Why:** A `'use server'` function is a public POST endpoint. Unlike `updateTaskStatus` (line 34), `deleteTask` never calls `requireProjectMember`, so any caller, signed in or not, who has a task UUID (they leak in URLs, logs, shared links) can delete tasks in projects they do not belong to. C1 data loss / R1 open.
**Fix:** Load the task's projectId first and call `await requireProjectMember(projectId)` before deleting, or delete with `where: { id, project: { members: { some: { userId: session.userId } } } }`.
**Cite:** CWE-862; CWE-639; OWASP A01:2021 Broken Access Control; Next.js docs, "Data Security" (Server Actions are public endpoints)
**Source:** model · confidence: high

### [blocker] `module_e.tsx:49` TS-SEC-04: Module-level QueryClient on the server shares prefetched tasks across requests and projects

```tsx
const serverQueryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
```

**Why:** `serverQueryClient` lives for the whole server process. Every `ProjectBoardPage` request prefetches into it and `dehydrate(serverQueryClient)` (line 59) serialises every cached query, so a member of project A receives project B's tasks in the HTML payload; with `staleTime: 60_000` the prefetch can also skip the fetch and serve cached data. Cross-tenant data leak, C1/R1 (X-SEV-01).
**Fix:** Create the client per request inside the page: `const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });` and dehydrate that one.
**Cite:** CWE-488; OWASP A01:2021 Broken Access Control; TanStack Query docs, "Advanced Server Rendering" (create the QueryClient per request)
**Source:** model · confidence: high

### [major] `module_c.tsx:55` TS-PERF-01: One author request per review inside a sequential loop (N+1 waterfall)

```tsx
const authorRes = await fetch(`/api/users/${review.authorId}`);
const author = (await authorRes.json()) as Author;
```

**Why:** Each review awaits its own `/api/users/:id` round trip before the next starts, so a product with 200 reviews makes 201 sequential requests before anything renders. Reviews per product grow without bound and this runs on every page view (C2/R1, X-SEV-02).
**Fix:** Collect unique author ids and fetch them in one batched request (`/api/users?ids=${ids.map(encodeURIComponent).join(',')}`), then join in memory.
**Cite:** CWE-1073; web.dev, "Avoid chaining critical requests"
**Source:** eslint (no-await-in-loop) · confidence: high

### [major] `module_c.tsx:63` TS-ERR-11: Reviews load has no error path: a failed request leaves the spinner forever

```tsx
load();
```

**Why:** `load()` is fired without `catch`, and inside it neither `fetch` (lines 51, 55) checks `res.ok` nor is there a `try/finally`. A 500, an HTML error page or a network failure rejects, `setLoading(false)` never runs, the user sees "Loading reviews..." forever and the rejection is unhandled. Main flow of the component (C2/R1).
**Fix:** Wrap the body in `try { ... if (!res.ok) throw new Error(`HTTP ${res.status}`) ... } catch (err) { setError(...) } finally { setLoading(false) }` and render an error state, or move the fetch into `useQuery` and use `isError`.
**Cite:** React docs, "Catching rendering errors with an error boundary" (async errors are not caught); WHATWG Fetch Standard (rejects only on network errors); CWE-755
**Source:** eslint (@typescript-eslint/no-floating-promises) · confidence: high

### [major] `module_c.tsx:64` TS-COR-11: Reviews effect ignores productId: navigating to another product keeps the old reviews

```tsx
}, []);
```

**Why:** The effect reads `productId` (line 51) but its dependency list is empty, so when the parent re-renders with a different product the component keeps showing the first product's reviews. Wrong data on screen on a common navigation (C2/R1).
**Fix:** Use `[productId]` and an `ignore` flag or `AbortController` cleanup so a late response for the old id cannot overwrite the new one (or use `useQuery` keyed by productId).
**Cite:** React docs, "Synchronizing with Effects"; React docs, "Removing Effect Dependencies"
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_c.tsx:69` TS-COR-16: Translations cached by review id only: changing targetLanguage shows the old language

```tsx
setTranslated((prev) => ({ ...prev, [review.id]: text }));
```

**Why:** `translated` is keyed by `review.id`, but the cached text depends on `targetLanguage` too. Assuming the prop changes when the user switches language (it is a prop for that reason), the review keeps showing the previous language's translation (line 101) with no way to tell. Wrong locale served (C2).
**Fix:** Key the cache by both inputs, e.g. `[`${review.id}:${targetLanguage}`]: text`, and read it with the same key.
**Cite:** TanStack Query docs, "Query Keys" (include every input in the key); CWE-524
**Source:** model · confidence: medium

### [major] `module_e.test.tsx:10` TS-TEST-07: Membership mock always returns a member; no test proves a non-member is rejected

```tsx
membership: { findUnique: vi.fn(async () => ({ role: 'member' })) },
```

**Why:** Every test runs with `findUnique` resolving to a membership, and no test calls `updateTaskStatus` or `deleteTask` as a non-member. The project's only test file therefore cannot fail when an authorization check is missing, which is exactly the `deleteTask` blocker (module_e.tsx:41). Untested denial of authorization logic (C2).
**Fix:** Add server-action tests that resolve `findUnique` to `null` and assert both actions reject and `db.task.update` / `db.task.delete` are not called.
**Cite:** OWASP ASVS 4.0.3 V4.1 (verify access control denies); Vitest docs, `vi.fn` mockResolvedValueOnce
**Source:** model · confidence: medium

### [major] `module_e.test.tsx:76` TS-TEST-02: 'moves a task to done' asserts that a mock function exists, which is always true

```tsx
expect(db.task.update).toBeDefined();
```

**Why:** `db.task.update` is a `vi.fn()` defined in the mock factory, so `toBeDefined()` passes whether the move worked, failed or never ran. This is the only test of the persisted status change, so a broken move ships green (C2, false confidence on a data-write path).
**Fix:** Make `findUniqueOrThrow` resolve a task, then `await waitFor(() => expect(db.task.update).toHaveBeenCalledWith({ where: { id: TASKS[0].id }, data: { status: 'done' } }))` and assert the card appears under "Done (1)".
**Cite:** Jest docs, "Expect" (`toBeDefined`, `toHaveBeenCalledWith`); Testing Library docs, "Async Methods"
**Source:** model · confidence: high

### [major] `module_e.tsx:85` TS-COR-11: UpdatedAgo interval captures updatedAt at mount, so the label never follows a changed task

```tsx
}, []);
```

**Why:** Both the initial state and the interval read `updatedAt` from the first render. After a move refetches the task with a new `updatedAt`, or after `key={index}` (line 167) hands this card a different task, the label keeps the old age on every 30 s tick: stale data on screen (C2/R1).
**Fix:** Add `updatedAt` to the dependency list and recompute immediately: `useEffect(() => { setLabel(formatAge(updatedAt)); const t = setInterval(...); return () => clearInterval(t); }, [updatedAt]);`
**Cite:** React docs, "Synchronizing with Effects"; React docs, "Removing Effect Dependencies"
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_e.tsx:118` TS-COR-12: Search effect fires a request per keystroke with no abort, so an older response can overwrite a newer one

```tsx
getTasks(projectId, term)
  .then((found) => { setSearchFailed(false); setResults(found); })
  .catch(() => setSearchFailed(true));
```

**Why:** Typing "release" starts seven requests; there is no AbortController or ignore flag, so if the response for "rel" arrives after the one for "release" the list shows the wrong results, and results from a previous project id can land after a switch. Visible stale data on a common path (C2/R1); the failure also sets `searchFailed` for aborted-by-nobody stale requests.
**Fix:** Create an `AbortController` in the effect, pass `ctrl.signal` to `getTasks`, ignore `AbortError`, and `return () => ctrl.abort();` (debounce the term as well), or use `useQuery` keyed by `[projectId, term]`.
**Cite:** React docs, "Synchronizing with Effects" (fetching data, cleanup); MDN, `AbortController`; CWE-772
**Source:** model · confidence: high

### [major] `module_e.tsx:138` TS-ERR-55: Optimistic task move has no rollback and only invalidates on success

```tsx
onMutate: async ({ taskId, status }) => {
  await queryClient.cancelQueries({ queryKey: tasksKey });
  queryClient.setQueryData<Task[]>(tasksKey, (prev) => prev?.map((t) => (t.id === taskId ? { ...t, status } : t)));
},
onSuccess: () => queryClient.invalidateQueries({ queryKey: tasksKey }),
```

**Why:** `onMutate` writes the new status into the cache without snapshotting the previous list, there is no `onError` restore, and invalidation runs only in `onSuccess`. When the Server Action fails (not a member, task deleted, network), the card stays in the new column, so the user believes the move was saved (C2/R1).
**Fix:** Snapshot with `const previous = queryClient.getQueryData<Task[]>(tasksKey); return { previous };`, restore it in `onError`, and move the invalidation to `onSettled`.
**Cite:** TanStack Query docs, "Optimistic Updates"
**Source:** model · confidence: high

### [major] `module_e.tsx:167` TS-COR-13: Task cards keyed by index while cards hold delete-confirmation state

```tsx
key={index}
```

**Why:** `TaskCard` keeps `confirmingDelete` in state. Columns are filtered lists that change on every move or delete, so the state stays with the position, not the task: click Delete on the first card, the task moves away, and the card that slides into that slot now shows "Confirm delete", one click from deleting the wrong task (C2/R1, wrong row's state).
**Fix:** Use the stable id: `key={task.id}`.
**Cite:** React docs, "Rendering Lists" (keys must not be array indexes when items move)
**Source:** eslint (react/no-array-index-key) · confidence: high

### [minor] `module_b.tsx:46` TS-COR-04: maximumFractionDigits is possibly undefined under strict, so the project fails type-checking

```tsx
return format.format(amountMinor / 10 ** digits);
```

**Why:** tsc reports TS18048 with the project's own tsconfig. At runtime ECMA-402 always resolves `maximumFractionDigits` for `style: 'currency'`, so amounts display correctly; the cost is a red `tsc --noEmit` in CI (C3).
**Fix:** `const digits = format.resolvedOptions().maximumFractionDigits ?? 2;` or read the currency's minor unit from data.
**Cite:** TypeScript handbook, "Narrowing"; MDN, `Intl.NumberFormat.prototype.resolvedOptions()`; CWE-476
**Source:** tsc (TS18048) · confidence: high

### [minor] `module_c.tsx:52` TS-MAINT-08: API responses cast with `as` instead of validated at the boundary

```tsx
const list = (await res.json()) as Review[];
```

**Why:** `as Review[]` (and `as Author`, line 56) only silences the compiler; an error body or a changed API shape flows into rendering, including the raw-HTML sink at line 101. Contained cost today, a crash or worse on the next API change (C3/R1).
**Fix:** Parse with the schema: `z.array(reviewSchema).parse(await res.json())` inside the error-handled path.
**Cite:** TypeScript handbook, "Type Assertions"; Zod docs, "Basic usage"
**Source:** model · confidence: high

### [minor] `module_c.tsx:59` TS-DIFF-01: console.log of every loaded review on each page view

```tsx
console.log('reviews loaded', withAuthors);
```

**Why:** Runs on every mount in production, dumping review and author objects into every visitor's console; no secrets, but unfiltered output on the main path (C3/R1, X-SEV-07).
**Fix:** Delete it, or use the project logger at debug level with ids only.
**Cite:** OWASP Logging Cheat Sheet; CWE-532
**Source:** eslint (no-console) · confidence: high

### [minor] `module_c.tsx:103` TS-ACC-01: Translate control is a clickable div that keyboard users cannot reach

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** No role, no tabIndex, no key handler: keyboard and many screen-reader users cannot translate a review. Secondary, optional action, so minor (X-SEV-06).
**Fix:** `<button type="button" className="review__translate" onClick={() => handleTranslate(review)}>Translate</button>`
**Cite:** WCAG 2.2 SC 2.1.1 Keyboard (A); WAI-ARIA APG, "Button pattern"
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:43` TS-TEST-06: it.only committed: local runs execute one test and skip the rest of the suite

```tsx
it.only('renders one column per status', async () => {
```

**Why:** With `.only`, Vitest runs just this test locally and reports green. In CI (`CI` set) Vitest's `allowOnly` defaults to false and the run fails instead of being narrowed, so the cost is a blocked pipeline and silently skipped tests for every developer (minor per the Vitest rule).
**Fix:** Remove `.only`: `it('renders one column per status', ...)`.
**Cite:** Vitest docs, `allowOnly`; Jest docs, `test.only`
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:53` TS-TEST-09: Test counts cards by CSS class through the container

```tsx
expect(container.querySelectorAll('.task-card')).toHaveLength(2);
```

**Why:** `container.querySelectorAll('.task-card')` breaks on a class rename and does not check anything a user sees (C3).
**Fix:** `expect(screen.getAllByRole('listitem').filter(...))` or assert each title with `screen.getByRole('heading', { name: 'Write release notes' })`.
**Cite:** Testing Library docs, "About Queries" (priority: getByRole first)
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:67` TS-TEST-02: user.type is not awaited, so the no-error assertion runs before any typing

```tsx
user.type(search, 'login');
expect(screen.queryByRole('alert')).not.toBeInTheDocument();
```

**Why:** `user.type` returns a promise; the assertion executes synchronously before the first keystroke and before any search request, so the test passes even if typing always shows the alert. The pending promise also leaks into the next test (C3).
**Fix:** `await user.type(search, 'login');` then `await waitFor(...)` or assert after the search response with `findBy*`.
**Cite:** user-event docs, "Introduction" (setup() and awaited calls); Testing Library docs, "Async Methods"
**Source:** model · confidence: high

### [minor] `module_e.tsx:163` TS-COR-72: Empty column renders a stray "0" because length is used on the left of &&

```tsx
{columnTasks.length && (
```

**Why:** `columnTasks.length && (...)` evaluates to `0` for an empty column and React renders it, so every empty column (Done, at start) shows a bare 0 under its heading (C3/R1).
**Fix:** `{columnTasks.length > 0 && (` or a ternary.
**Cite:** React docs, "Conditional Rendering" (do not put numbers on the left of &&)
**Source:** eslint (react/jsx-no-leaked-render) · confidence: high

### [nit] `module_a.tsx:115` TS-ACC-09: aria-label on a role-less span is ignored by many screen readers

```tsx
<span className="review__rating" aria-label={`${review.rating} out of 5 stars`}>
```

**Why:** Naming is prohibited on a generic `<span>`, so assistive tech may read "black star" glyphs instead of "4 out of 5 stars". Visible text partly conveys it, so nit.
**Fix:** Add `role="img"` to the span (or render visually hidden text).
**Cite:** WAI-ARIA 1.2 (naming prohibited on generic); WCAG 2.2 SC 4.1.2 Name, Role, Value (A)
**Source:** model · confidence: high

### [nit] `module_c.tsx:92` TS-ACC-09: aria-label on a role-less span is ignored by many screen readers

```tsx
<span className="review__rating" aria-label={`${review.rating} out of 5 stars`}>
```

**Why:** Same as the rating span elsewhere: naming is prohibited on a generic `<span>`; the stars glyphs carry partial meaning, so nit.
**Fix:** Add `role="img"` to the span.
**Cite:** WAI-ARIA 1.2 (naming prohibited on generic); WCAG 2.2 SC 4.1.2 Name, Role, Value (A)
**Source:** model · confidence: high

### [nit] 2 nits from eslint

Collapsed because eslint reports them (no-unused-vars): unused React imports at `module_c.tsx:1`, `module_e.tsx:1`. Run `eslint --fix` or delete the unused names.

## Questions

- `module_e.tsx:6` — This module imports the database client and defines Server Actions, yet `TaskBoard`, `TaskSearch` and `UpdatedAgo` use hooks and are rendered from the server component `ProjectBoardPage`. Is `TaskBoard` split into a `'use client'` file in the real app? If this file is marked `'use client'`, `@/lib/db` is bundled for the browser and the inline `'use server'` actions are rejected; if it is not, the hooks throw when rendered on the server (TS-COR-74; Next.js docs, `server-only`).

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
