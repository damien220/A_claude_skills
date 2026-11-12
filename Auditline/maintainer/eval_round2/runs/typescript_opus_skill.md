# Auditline report

**Scope:** file `module_a.tsx`, `module_b.tsx`, `module_c.tsx`, `module_e.tsx`, `module_e.test.tsx` (no git context) · **Mode:** full · **Languages:** typescript
**Tools:** eslint: ran (bundled fallback config) | tsc: ran (project tsconfig.json; 8 environment errors discarded, see JSON notes)
**Coverage:** all files in scope (5 of 5); `module_a.tsx` and `module_b.tsx` have no findings

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 10 | 6 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.tsx:25` TS-SEC-02: Live translation API key hardcoded in browser code and sent as a Bearer token

```tsx
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';
```

**Why:** Consequence C1: `tr_live_…` is a production credential (sent as `Authorization: Bearer` at line 32). This is a client component, so the literal ships in the JavaScript bundle to every visitor and stays in git history; anyone can bill or abuse the translation account. Reachability is irrelevant for a committed secret (X-SEV-04, never downgraded).
**Fix:** Remove the key from the client; call an own backend route (`POST /api/reviews/:id/translate`) that reads the key from a server-side environment variable, as the sibling component does. Rotate the leaked key now.
**Cite:** CWE-798; CWE-200; OWASP A07:2021 Identification and Authentication Failures; OWASP Secrets Management Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_c.tsx:101` TS-SEC-16: Review body and third-party translation output rendered as raw HTML

```tsx
dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
```

**Why:** Consequence C1: `review.body` is text written by other customers and `translated[...]` is third-party API output; both reach `dangerouslySetInnerHTML` unsanitized, so a review containing `<img src=x onerror=…>` runs script in every visitor's session (stored XSS). Reachability R1: any customer who can post a review. X-SEV-04 class, never downgraded.
**Fix:** Render as text: `<p className="review__body">{translated[review.id] ?? review.body}</p>`; if HTML is truly required, pass it through `DOMPurify.sanitize()` unchanged.
**Cite:** CWE-79; OWASP A03:2021 Injection; OWASP Cross Site Scripting Prevention Cheat Sheet; React docs, `dangerouslySetInnerHTML`
**Source:** eslint (react/no-danger) · confidence: high

### [blocker] `module_e.tsx:43` TS-SEC-04: deleteTask server action deletes any task by id with no session or membership check

```tsx
const id = z.string().uuid().parse(taskId);
const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
```

**Why:** Consequence C1: `'use server'` functions are public POST endpoints, and `deleteTask` deletes by the client-supplied id alone; unlike `updateTaskStatus` (line 34) it never calls `requireProjectMember`, so any caller, even one with no session, can delete tasks in projects they do not belong to (ids leak through URLs and shared boards). Reachability R1 (authorization bypass, X-SEV-04).
**Fix:** Look up the task's `projectId` first, call `await requireProjectMember(projectId)`, then delete; or `deleteMany({ where: { id, project: { members: { some: { userId: session.userId } } } } })` and 404 on zero rows.
**Cite:** CWE-862; CWE-639; OWASP A01:2021 Broken Access Control; Next.js docs, "Data Security" (Server Actions are public endpoints)
**Source:** model · confidence: high

### [blocker] `module_e.tsx:49` TS-SEC-04: Module-level QueryClient on the server is shared by every request, leaking other projects' tasks

```tsx
const serverQueryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
```

**Why:** Consequence C1: `serverQueryClient` lives at module scope and `ProjectBoardPage` prefetches into it and dehydrates the whole client (line 59), so every page render ships every cached `['tasks', <projectId>]` entry from earlier requests, other users' projects included, into this user's HTML payload; `staleTime` also serves a 60 s old list. Reachability R1: any member of any project who opens a board.
**Fix:** Create the client per request inside the page: `const queryClient = new QueryClient(…)` in `ProjectBoardPage` (or a `cache()`-scoped getter).
**Cite:** CWE-488; OWASP A01:2021 Broken Access Control; TanStack Query docs, "Advanced Server Rendering" (create the QueryClient per request)
**Source:** model · confidence: high

### [major] `module_c.tsx:51` TS-ERR-11: Reviews load has no status check and no try/finally, so a failed request leaves the spinner on forever

```tsx
const res = await fetch(`/api/products/${productId}/reviews`);
const list = (await res.json()) as Review[];
```

**Why:** Consequence C2: `fetch` resolves on 404/500 and `res.json()` then throws on an HTML error page (or casts an error body to `Review[]`); any throw in `load()` skips `setLoading(false)` at line 61, so the page shows "Loading reviews…" forever with no error message, and the rejection is unhandled because `load()` at line 63 is not awaited or caught (eslint no-floating-promises, merged here). The same applies to each author fetch at line 55. Reachability R1: every product page view when the API or one author lookup fails (e.g. a deleted user).
**Fix:** Wrap the body in `try { … if (!res.ok) throw new Error(`HTTP ${res.status}`) … } catch (err) { setError(…) } finally { setLoading(false) }` and render an error state with `role="alert"`; better, move the fetch into TanStack Query (`useQuery` with `isError`).
**Cite:** React docs, "Catching rendering errors with an error boundary" (boundaries do not catch async errors); TanStack Query docs, "Queries" (`isError`); WHATWG Fetch Standard (rejects only on network errors); CWE-755
**Source:** model · confidence: high

### [major] `module_c.tsx:55` TS-PERF-01: One sequential author request per review (N+1) on every page load

```tsx
const authorRes = await fetch(`/api/users/${review.authorId}`);
const author = (await authorRes.json()) as Author;
```

**Why:** Consequence C2: the loop awaits `/api/users/:id` once per review, sequentially, so a product with 200 reviews makes 201 round trips before anything renders; reviews per product are unbounded and grow over time. Reachability R1: every product page view (X-SEV-02: major).
**Fix:** Fetch the unique author ids in one batched request (`/api/users?ids=…` with `encodeURIComponent`), then join in memory with a `Map`.
**Cite:** CWE-1073; web.dev, "Avoid chaining critical requests"
**Source:** eslint (no-await-in-loop) · confidence: high

### [major] `module_c.tsx:64` TS-COR-11: Reviews effect ignores productId, so another product's reviews stay on screen

```tsx
}, []);
```

**Why:** Consequence C2: `load` reads `productId` but the dependency list is `[]`, so when the component is re-rendered with a new `productId` (client-side navigation between products) the old product's reviews stay on screen. Once the dependency is added, the fetch also needs an `ignore` flag or `AbortController` so a slow earlier response cannot overwrite a newer one. Reachability R1: any navigation from one product to another that keeps the component mounted.
**Fix:** `}, [productId]);` with `let ignore = false; … return () => { ignore = true; };`, or use `useQuery({ queryKey: ['product-reviews', productId], … })`.
**Cite:** React docs, "Synchronizing with Effects"; React docs, "Removing Effect Dependencies"
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_c.tsx:69` TS-COR-16: Translations cached by review id only, so a language change keeps showing the old language

```tsx
setTranslated((prev) => ({ ...prev, [review.id]: text }));
```

**Why:** Consequence C2: `translated` is keyed by `review.id` but the result also depends on `targetLanguage`; after the user (or the parent) switches the target language, line 101 keeps showing the earlier translation for every review already translated, and the failure text from line 71 is cached the same way. Reachability R1: any user who changes language after translating.
**Fix:** Key by both inputs: `const key = `${review.id}:${targetLanguage}`;` in `setTranslated` and in the read at line 101.
**Cite:** TanStack Query docs, "Query Keys" (every input the result depends on belongs in the key)
**Source:** model · confidence: medium

### [major] `module_e.test.tsx:76` TS-TEST-02: Move test asserts only that a vi.fn() mock is defined

```tsx
expect(db.task.update).toBeDefined();
```

**Why:** Consequence C2: `db.task.update` is a mock created in `vi.mock`, so `toBeDefined()` is always true; the test passes if the move never reaches the server, if the status is wrong, or if the action throws (it does: the mocked `findUniqueOrThrow` returns `undefined`, so destructuring `projectId` fails). It is the only test of the persistence path (moving a task).
**Fix:** Give `findUniqueOrThrow` a resolved value, then assert the outcome: `await waitFor(() => expect(db.task.update).toHaveBeenCalledWith({ where: { id: TASKS[0].id }, data: { status: 'done' } }))` and the card's new column heading count.
**Cite:** Jest docs, `.resolves` / `.rejects`; pytest docs, "Asserting with the `assert` statement" (assert the specific value)
**Source:** model · confidence: high

### [major] `module_e.tsx:6` TS-COR-74: Database client and server actions share a module with hook-based client components and no client/server boundary

```tsx
import { db } from '@/lib/db';
```

**Why:** Consequence C2: the module imports `db`, `getSession` and `logger` and defines server actions, but `TaskBoard`, `TaskSearch`, `TaskCard` and `UpdatedAgo` use `useState`/`useQuery`/`useMutation`, and `ProjectBoardPage` renders `TaskBoard` directly. Without `'use client'` the hooks run in a Server Component and Next.js fails the render; with it, the db client and logger are bundled into browser JavaScript and inline `'use server'` functions are not allowed. Assumption: this is a Next.js App Router file, as the `next/cache` import shows. Reachability R1: every board page.
**Fix:** Split the file: server actions in `actions.ts` with a top-level `'use server'` and `import 'server-only'` in `@/lib/db`; client UI in a `'use client'` module that imports the actions; the page stays a Server Component that renders the client board.
**Cite:** Next.js docs, "Server and Client Components: Keeping server-only code out of the client environment" (the `server-only` package)
**Source:** model · confidence: medium

### [major] `module_e.tsx:85` TS-COR-11: UpdatedAgo interval keeps formatting the mount-time updatedAt

```tsx
}, []);
```

**Why:** Consequence C2: the interval reads `updatedAt` captured at mount (deps `[]`), and the label state is initialised once, so after a task moves (new `updatedAt`) or the card is reused for another task (index keys, line 167) the card shows another moment's or another task's age indefinitely. Reachability R1: every status change on the board.
**Fix:** Add `updatedAt` to the dependencies and reset the label inside the effect: `setLabel(formatAge(updatedAt));` before starting the interval.
**Cite:** React docs, "Synchronizing with Effects"; React docs, "Removing Effect Dependencies"
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_e.tsx:118` TS-COR-12: Search request per keystroke with no abort or ignore flag; older responses overwrite newer results

```tsx
getTasks(projectId, term)
  .then((found) => { setSearchFailed(false); setResults(found); })
  .catch(() => setSearchFailed(true));
```

**Why:** Consequence C2: each keystroke starts a request and nothing cancels the previous one, so a slow response for "rel" can arrive after "release" and replace the correct results (and set the error flag for a search the user already left). Reachability R1: every search; responses arrive in any order.
**Fix:** `const ctrl = new AbortController(); getTasks(projectId, term, ctrl.signal)… .catch((e) => { if (e.name !== 'AbortError') setSearchFailed(true); }); return () => ctrl.abort();` (and debounce the term), or use `useQuery({ queryKey: ['tasks', projectId, term], enabled: term !== '' })`.
**Cite:** React docs, "Synchronizing with Effects" (fetching data, cleanup); MDN, `AbortController`; CWE-772
**Source:** model · confidence: high

### [major] `module_e.tsx:138` TS-ERR-55: Optimistic task move has no snapshot, no rollback on error and no settle

```tsx
onMutate: async ({ taskId, status }) => {
  await queryClient.cancelQueries({ queryKey: tasksKey });
  queryClient.setQueryData<Task[]>(tasksKey, (prev) => prev?.map((t) => (t.id === taskId ? { ...t, status } : t)));
```

**Why:** Consequence C2: `onMutate` writes the new status into the cache, but there is no `onError` restoring a snapshot and invalidation runs only `onSuccess`, so when the server action rejects (not a member, validation, network) the card stays in the new column while the server keeps the old status; the user believes the move was saved. Reachability R1: every failed move.
**Fix:** Return `{ previous: queryClient.getQueryData<Task[]>(tasksKey) }` from `onMutate`, add `onError: (_e, _v, ctx) => queryClient.setQueryData(tasksKey, ctx?.previous)`, and move the invalidation to `onSettled`.
**Cite:** TanStack Query docs, "Optimistic Updates"
**Source:** model · confidence: high

### [major] `module_e.tsx:167` TS-COR-13: Task cards keyed by index while they hold delete-confirmation state

```tsx
key={index}
```

**Why:** Consequence C2: `TaskCard` keeps `confirmingDelete` in state; with `key={index}`, when a task leaves or enters the column (a move, a delete, a refetch) the state stays at the position, so a card the user never touched shows "Confirm delete" and one click deletes the wrong task. Reachability R1: any board where tasks move while a confirmation is open.
**Fix:** `key={task.id}`.
**Cite:** React docs, "Rendering Lists" (keys must be stable ids from the data)
**Source:** eslint (react/no-array-index-key) · confidence: high

### [minor] `module_c.tsx:59` TS-DIFF-01: console.log of the full review list on every page load

```tsx
console.log('reviews loaded', withAuthors);
```

**Why:** Consequence C3: unleveled debug output of every review with its author object in each visitor's console, bypassing any logger; no secrets, so not U4. Reachability R1: runs on every product page load (X-SEV-07: minor).
**Fix:** Delete the line, or use the project logger at debug level.
**Cite:** CWE-532; OWASP Logging Cheat Sheet
**Source:** eslint (no-console) · confidence: high

### [minor] `module_c.tsx:103` TS-ACC-01: Translate action is a clickable div with no role, focus or key handler

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** Consequence C3: keyboard and many screen-reader users cannot reach or activate "Translate"; it is a secondary action, so the core flow (reading reviews) still works (X-SEV-06: minor, like worked example m4). Reachability R1.
**Fix:** `<button type="button" className="review__translate" onClick={() => void handleTranslate(review)}>Translate</button>`
**Cite:** WCAG 2.2 SC 2.1.1 Keyboard (A); WAI-ARIA APG, "Button pattern"
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:43` TS-TEST-06: Committed it.only narrows the TaskBoard suite to one test

```tsx
it.only('renders one column per status', async () => {
```

**Why:** Consequence: locally only this test runs and the other four are skipped; Vitest fails the run when `CI` is set (`allowOnly` defaults to `!process.env.CI`), so CI is not silently narrowed, but every local run is (rule TS-TEST-06: minor under Vitest).
**Fix:** `it('renders one column per status', async () => {`
**Cite:** Vitest docs, `allowOnly`; Jest docs, `test.only`
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:53` TS-TEST-09: Card count asserted through a CSS class query on the container

```tsx
expect(container.querySelectorAll('.task-card')).toHaveLength(2);
```

**Why:** Consequence C3: the test breaks on a class rename and passes on markup a screen-reader user cannot navigate; a role query would check the list items users see. Reachability R3 (test code), rated on the coverage it weakens.
**Fix:** `expect(within(screen.getByRole('region', { name: 'To do' })).getAllByRole('listitem')).toHaveLength(1)` or query the task titles.
**Cite:** Testing Library docs, "Guiding Principles" and "About Queries" (priority: `getByRole` first)
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:67` TS-TEST-09: user.type is not awaited, so the assertion runs before any typing happens

```tsx
user.type(search, 'login');
```

**Why:** Consequence: the `expect` on line 68 runs before a single key is typed or a search request starts, so the test passes whatever the search does and can only fail on a mount-time alert; the pending typing also leaks into teardown. The search error path is effectively untested.
**Fix:** `await user.type(search, 'login');` then `expect(await screen.findByRole('listitem', …))` or `await waitFor(…)` before asserting there is no alert.
**Cite:** user-event docs, "Introduction" (`setup()` and awaited calls); Testing Library docs, "About Queries"
**Source:** eslint (@typescript-eslint/no-floating-promises) · confidence: high

### [minor] `module_e.tsx:163` TS-COR-72: Empty column renders a stray 0 from `columnTasks.length &&`

```tsx
{columnTasks.length && (
```

**Why:** Consequence C3: for a column with no tasks React renders the number `0` under the heading ("Done (0)" followed by "0"). Reachability R1: every empty column, which is the common state for "Done" on a new project.
**Fix:** `{columnTasks.length > 0 && (` or a ternary.
**Cite:** React docs, "Conditional Rendering" (do not put numbers on the left side of `&&`)
**Source:** eslint (react/jsx-no-leaked-render) · confidence: high

### [nit] 2 nits from eslint

Collapsed because eslint reports them (`no-unused-vars`: `module_c.tsx:1`, `module_e.tsx:1`). Run `npx eslint --fix` or remove the unused imports.

## Questions

Low-confidence blockers or majors, and absence-of-control items, go here, not above. Questions do not change the verdict.

- `module_e.tsx:20` - Is `requireProjectMember` (and the missing check in `deleteTask`) covered by a test elsewhere? The only test file in scope renders `TaskBoard` and never proves that a non-member is rejected; if no other test does, the authorization logic has no denial test (TS-TEST-07, OWASP ASVS 4.0.3 V4.1).
- `module_c.tsx:51` - Where does `productId` come from? It is interpolated into the path without `encodeURIComponent`; if it is taken from the URL, a value like `../users/x` sends the request (with cookies) to another same-origin endpoint whose JSON is then rendered as HTML at line 101.

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
