# Auditline report

**Scope:** files `module_a.tsx`, `module_b.tsx`, `module_c.tsx`, `module_e.tsx`, `module_e.test.tsx` (file scope, nothing is pre-existing) · **Mode:** full · **Languages:** typescript
**Tools:** eslint: ran (bundled fallback config) | tsc: ran (project tsconfig.json); discarded results and reasons are in the JSON `tools` notes
**Coverage:** all files in scope

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 10 | 8 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.tsx:25` TS-SEC-02: Live translation API key hardcoded in browser code

```tsx
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';
```

**Why:** A `tr_live_` credential is committed in a client component and sent as `Authorization: Bearer` on line 32, so it ships in the JavaScript bundle to every visitor and stays in git history. Consequence: anyone can spend the translation quota or abuse the account; reachability: every page view, no precondition.
**Fix:** Move the call behind an own API route that reads the key from `process.env` on the server (as module_a.tsx does with `/api/reviews/:id/translate`), and rotate the leaked key.
**Cite:** CWE-798; CWE-200; OWASP A07:2021 Identification and Authentication Failures; Next.js docs, "Environment Variables" (values in client code are inlined into the browser bundle)
**Source:** model · confidence: high

### [blocker] `module_c.tsx:101` TS-SEC-16: Review text and translation rendered as raw HTML

```tsx
dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
```

**Why:** `review.body` is written by other customers and the translation comes from a third-party API; both are injected as HTML on every product page that lists reviews. A review containing `<img src=x onerror=...>` runs script in every visitor's session (stored XSS, open to anyone who can post a review).
**Fix:** Render as text: `<div className="review__body">{translated[review.id] ?? review.body}</div>`; if HTML is required, sanitize with DOMPurify.
**Cite:** CWE-79; OWASP A03:2021 Injection; React docs, `dangerouslySetInnerHTML`; OWASP Cross Site Scripting Prevention Cheat Sheet
**Source:** eslint (react/no-danger) · confidence: high

### [blocker] `module_e.tsx:44` TS-SEC-04: deleteTask Server Action deletes by id with no session or membership check

```tsx
const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
```

**Why:** `'use server'` functions are public POST endpoints. `updateTaskStatus` calls `requireProjectMember(projectId)`, but `deleteTask` never looks at the session, so anyone who can post to the action, including a signed-out visitor, can delete any task whose UUID they have seen (IDs also leak in URLs, logs and the dehydrated page state). The test file never exercises this path.
**Fix:** Look up the task's `projectId` first and `await requireProjectMember(projectId)` before deleting (as `updateTaskStatus` does), or delete with `where: { id, project: { members: { some: { userId: session.userId } } } }`; add a test that a non-member is rejected.
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; Next.js docs, "Data Security" (Server Actions are public endpoints)
**Source:** model · confidence: high

### [blocker] `module_e.tsx:49` TS-SEC-04: Module-level QueryClient on the server dehydrates every project's cached tasks to each visitor

```tsx
const serverQueryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
```

**Why:** `ProjectBoardPage` is a server component (async, calls `db`), and one `serverQueryClient` is shared by every request. `prefetchQuery` fills it with `['tasks', projectId]` for each project any member opens, and `dehydrate(serverQueryClient)` serialises all queries in the cache into the HTML, so a member of project A receives project B's tasks that another user prefetched in the last minute and later (queries stay cached). Cross-tenant data exposure, open to any signed-in user.
**Fix:** Create the client inside the request: `const queryClient = new QueryClient(...)` in `ProjectBoardPage`, prefetch and `dehydrate(queryClient)` on that instance.
**Cite:** TanStack Query docs, "Advanced Server Rendering" (create the QueryClient per request to avoid sharing data between users); CWE-488; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [major] `module_c.tsx:51` TS-ERR-11: Loading flag never reset and failures unhandled when the review fetch fails

```tsx
const res = await fetch(`/api/products/${productId}/reviews`);
```

**Why:** `load()` has no `try/finally` and no `res.ok` check: when `fetch` or `res.json()` throws, `setLoading(false)` on line 61 never runs and the page shows "Loading reviews…" forever; an HTTP 500 is parsed as a review list (`list` is not iterable). The call on line 63 is also an un-awaited, un-caught promise (eslint no-floating-promises), so the rejection is unhandled and the user gets no error state. Reachable on any network or server error, on a main flow.
**Fix:** Wrap the body in `try { ... if (!res.ok) throw new Error(...) ... } catch { setError(...) } finally { setLoading(false); }`, render an error state with `role="alert"`, and call `void load()`; or use `useQuery` and its `isError`.
**Cite:** React docs, "Catching rendering errors with an error boundary" (boundaries do not catch async errors); TanStack Query docs, "Queries" (`isError`); WHATWG Fetch Standard (the promise rejects only on network errors); CWE-755
**Source:** model · confidence: high

### [major] `module_c.tsx:55` TS-PERF-01: One sequential author request per review (N+1)

```tsx
const authorRes = await fetch(`/api/users/${review.authorId}`);
```

**Why:** The loop awaits one `/api/users/:id` round trip per review, one after another, with no cap on reviews per product (eslint no-await-in-loop on lines 55 and 56). Page load time grows linearly with the review count on a product page, for every visitor. module_a.tsx batches this into one `/api/users?ids=` call.
**Fix:** Fetch authors in one batched request (`/api/users?ids=...`) for the unique `authorId` values, then join in memory.
**Cite:** CWE-1073; web.dev, "Avoid chaining critical requests"; eslint docs, `no-await-in-loop`
**Source:** eslint (no-await-in-loop) · confidence: high

### [major] `module_c.tsx:64` TS-COR-11: Effect reads productId but its dependency array is empty

```tsx
}, []);
```

**Why:** The effect fetches reviews for `productId` (line 51) but runs only on mount, so when the product prop changes the previous product's reviews stay on screen while the heading and page show the new product. Reachable whenever the component is reused across products. Once the dependency is added, the effect also needs an `ignore` flag or `AbortController` so a slow earlier response cannot overwrite a newer one.
**Fix:** Use `}, [productId]);` with a cleanup (`let ignore = false; ... return () => { ignore = true; }`), or move the fetch to `useQuery` with `['product-reviews', productId]` as module_a.tsx does.
**Cite:** React docs, "Synchronizing with Effects", "Removing Effect Dependencies"
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_c.tsx:69` TS-COR-16: Translations stored by review id only, ignoring the target language

```tsx
setTranslated((prev) => ({ ...prev, [review.id]: text }));
```

**Why:** The translated text is keyed by `review.id` alone and rendered back on line 101, so after the `targetLanguage` prop changes (for example fr to de) each already-translated review keeps showing the old language and the user cannot get the new one without a reload. Assumes `targetLanguage` can change while mounted, which a prop allows; module_a.tsx keys by id and target.
**Fix:** Key the map by id and language (`${review.id}:${targetLanguage}`) as module_a.tsx's `translationKey` does, or clear `translated` when `targetLanguage` changes.
**Cite:** TanStack Query docs, "Query Keys" (include every input the result depends on); CWE-524
**Source:** model · confidence: medium

### [major] `module_e.test.tsx:67` TS-TEST-02: Un-awaited user.type: the no-error assertion runs before any typing

```tsx
user.type(search, 'login');
```

**Why:** `userEvent` calls return promises; without `await` the next line asserts `queryByRole('alert')` is absent before a single key was typed, so the test passes whatever the component does while typing. It is the only test of the search error state, so a broken or erroring search would still be green.
**Fix:** `await user.type(search, 'login');` and then assert, using `waitFor` or `findBy*` for async outcomes.
**Cite:** user-event docs, "Introduction" (`setup()` and awaited calls); Testing Library docs, "Guiding Principles"
**Source:** eslint (@typescript-eslint/no-floating-promises) · confidence: high

### [major] `module_e.test.tsx:76` TS-TEST-02: Assertion `toBeDefined()` on a mock that is always defined

```tsx
expect(db.task.update).toBeDefined();
```

**Why:** `db.task.update` is a `vi.fn()` created in `vi.mock`, so it is defined whether or not the move happened. The test never asserts that `update` was called with `status: 'done'` or that the card moved, and `findUniqueOrThrow` is a bare `vi.fn()` returning `undefined`, so the action throws and the test still passes. It is the only test of the move flow.
**Fix:** Assert the outcome: `expect(db.task.update).toHaveBeenCalledWith({ where: { id }, data: { status: 'done' } })` after configuring `findUniqueOrThrow`, and that the card appears under "Done".
**Cite:** Vitest docs, `expect` / `toHaveBeenCalledWith`; Google Testing Blog, "Testing on the Toilet: Test Behavior, Not Implementation"
**Source:** model · confidence: high

### [major] `module_e.tsx:85` TS-COR-11: UpdatedAgo effect reads updatedAt but its dependency array is empty

```tsx
}, []);
```

**Why:** The interval callback captures the `updatedAt` of the first render, so after a task is edited and refetched (new `updatedAt`) the label keeps counting from the old timestamp and shows "Updated 5 minutes ago" for a task just changed. Also the label is only refreshed after 30 s.
**Fix:** Use `}, [updatedAt]);` and set the label immediately inside the effect, or compute the age in render from a ticking `now` state.
**Cite:** React docs, "Synchronizing with Effects", "Removing Effect Dependencies"
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_e.tsx:118` TS-COR-12: Search effect fetches without abort or ignore flag

```tsx
getTasks(projectId, term)
```

**Why:** Each keystroke starts a request whose result is written with `setResults`, with no `AbortController` or `ignore` flag and no debounce, so a slow response for "ab" can resolve after "abc" and overwrite the newer results; clearing the box (line 114) can also be overwritten by an in-flight response. Reachable by anyone typing quickly.
**Fix:** Pass an `AbortSignal` to `getTasks` and return a cleanup that aborts (or sets `ignore`), or use `useQuery` with `['tasks', projectId, 'search', term]` and `enabled: term.trim() !== ''`.
**Cite:** React docs, "Synchronizing with Effects" (fetching data, cleanup); MDN, `AbortController`; CWE-772
**Source:** model · confidence: high

### [major] `module_e.tsx:138` TS-ERR-55: Optimistic move writes the cache with no rollback and no settle

```tsx
onMutate: async ({ taskId, status }) => {
```

**Why:** `onMutate` moves the task in the cache with `setQueryData`, but `moveTask` has no `onError` to restore a snapshot and invalidates only in `onSuccess`. When `updateTaskStatus` rejects (for example a non-member or a deleted task), the card stays in the wrong column while only "Your last change was not saved." appears, until a manual reload.
**Fix:** Snapshot with `getQueryData` in `onMutate` and return it as context, restore it in `onError`, and invalidate in `onSettled`.
**Cite:** TanStack Query docs, "Optimistic Updates"
**Source:** model · confidence: high

### [major] `module_e.tsx:167` TS-COR-13: Task cards keyed by array index in a list that moves, filters and holds per-card state

```tsx
key={index}
```

**Why:** Each `TaskCard` owns `confirmingDelete` state and an `UpdatedAgo` interval. Moving a task (optimistic update, line 140) or deleting one shifts the following cards up one index, so the next card inherits "Confirm delete" and one click on it deletes a different task. Raised from the tool's minor because the wrong row's state is shown and acted on.
**Fix:** Use `key={task.id}`.
**Cite:** React docs, "Rendering Lists" (keys); React docs, "Preserving and Resetting State"
**Source:** eslint (react/no-array-index-key) · confidence: high

### [minor] `module_c.tsx:52` TS-MAINT-08: API responses asserted with `as` instead of validated

```tsx
const list = (await res.json()) as Review[];
```

**Why:** `as Review[]` (and `as Author` on line 56, `as { translation: string }` on line 39) only silences the compiler; a changed or error payload reaches the render code unchecked (for example `review.author.avatarUrl` on a missing author). module_a.tsx parses each response with zod at the boundary.
**Fix:** Parse with a zod schema (`z.array(reviewSchema).parse(await res.json())`) inside the fetch function.
**Cite:** TypeScript handbook, "Everyday Types: Type Assertions" (assertions are removed at compile time); Zod docs, "Basic usage"
**Source:** model · confidence: high

### [minor] `module_c.tsx:59` TS-DIFF-01: console.log of every loaded review on each page load

```tsx
console.log('reviews loaded', withAuthors);
```

**Why:** Debug output runs on every mount of a customer-facing component and dumps all reviews with author names and avatar URLs into the browser console, bypassing any logger.
**Fix:** Delete it, or use the project logger at debug level without user data.
**Cite:** CWE-532; CWE-489 (active debug code)
**Source:** eslint (no-console) · confidence: high

### [minor] `module_c.tsx:70` TS-ERR-01: Translation failure caught, not logged, and error text replaces the review body

```tsx
} catch {
```

**Why:** The catch stores 'Translation unavailable.' in the `translated` map, which line 101 renders in place of `review.body`, so a failed translation hides the customer's original review and nothing is logged or retried. Triggered by any translation API failure.
**Fix:** Keep the original body, track the failure separately (`translation.isError` or an error map) and show a `role="alert"` message; log the error.
**Cite:** CWE-390; CWE-391
**Source:** model · confidence: high

### [minor] `module_c.tsx:103` TS-ACC-01: Translate control is a div with a click handler only

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** A `div` with `onClick` has no role, no `tabIndex` and no key handler, so keyboard and screen-reader users cannot reach or activate Translate (WCAG 2.1.1, Level A). It is a secondary control on each review, so minor.
**Fix:** Use `<button type="button" className="review__translate" onClick={...}>Translate</button>`.
**Cite:** WCAG 2.2 SC 2.1.1 Keyboard (A); WAI-ARIA APG, "Button pattern"
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:43` TS-TEST-06: Focused test `it.only` narrows the suite to one test

```tsx
it.only('renders one column per status', async () => {
```

**Why:** Every other test in the file is silently skipped while `.only` is present. Vitest sets `allowOnly` to false when `CI` is set, so CI would fail rather than narrow (assuming no config override, none is shown), but local runs stay green with four tests skipped.
**Fix:** Remove `.only`.
**Cite:** Vitest docs, `test.only` and `allowOnly`
**Source:** model · confidence: medium

### [minor] `module_e.test.tsx:53` TS-TEST-09: Test queries the DOM by CSS class through container

```tsx
expect(container.querySelectorAll('.task-card')).toHaveLength(2);
```

**Why:** Selecting by a class name couples the test to markup that users never see, and breaks on a refactor that changes nothing for them.
**Fix:** Query by role: `expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(2)` or by the task titles.
**Cite:** Testing Library docs, "Guiding Principles" and "About Queries"
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:60` TS-TEST-03: Search test passes because the fetch mock ignores the query

```tsx
await waitFor(() => expect(screen.getAllByText('Write release notes')).toHaveLength(2));
```

**Why:** The `fetch` spy returns all `TASKS` for every URL, so the "matching" list is just the mock's fixture (it also contains the non-matching 'Fix login redirect'). The test would pass if the `q` parameter were never sent or the search were broken.
**Fix:** Make the mock respond by URL (return only tasks matching `q`) and assert the request contained `q=release`.
**Cite:** Google Testing Blog, "Testing on the Toilet: Test Behavior, Not Implementation"; Vitest docs, `vi.spyOn`
**Source:** model · confidence: medium

### [minor] `module_e.tsx:163` TS-COR-72: Array length on the left of && renders a stray 0

```tsx
{columnTasks.length && (
```

**Why:** An empty column renders the number `0` under its heading instead of nothing, because React renders `0`.
**Fix:** Use `columnTasks.length > 0 && (...)` or a ternary.
**Cite:** React docs, "Conditional Rendering" (do not put numbers on the left side of `&&`)
**Source:** eslint (react/jsx-no-leaked-render) · confidence: high

### [nit] `module_c.tsx:1` TS-MAINT-01: Unused import `useMemo`

```tsx
import { useEffect, useMemo, useState } from 'react';
```

**Why:** `useMemo` is imported and never used; reader cost only.
**Fix:** Remove it from the import (`eslint --fix` / editor organise imports).
**Cite:** ESLint docs, `no-unused-vars`; X-SEV-08
**Source:** eslint (no-unused-vars) · confidence: high

### [nit] `module_e.tsx:1` TS-MAINT-01: Unused import `useCallback`

```tsx
import { useCallback, useEffect, useState } from 'react';
```

**Why:** `useCallback` is imported and never used; reader cost only.
**Fix:** Remove it from the import.
**Cite:** ESLint docs, `no-unused-vars`; X-SEV-08
**Source:** eslint (no-unused-vars) · confidence: high

## Questions

Low-confidence blockers or majors, and absence-of-control items, go here, not above. Questions do not change the verdict.

- `module_e.tsx:5` — `@/lib/auth`, `@/lib/db` and `@/lib/logger` are imported, but tsconfig.json declares no `paths` (tsc reports TS2307). Is the alias mirrored in the real bundler and test-runner config? If not, the build and the tests fail with "Cannot find module" (TS-COR-78).
- `module_e.tsx:6` — This file imports the `db` client and also exports hook-using client components (`TaskBoard`, `TaskSearch`) with no `'use client'` or `import 'server-only'`. Are the server code and the client UI split into separate modules in the real project? If the file is marked client, `db` ends up in the browser bundle (TS-COR-74).

## Pre-existing (not part of this change)

None (file scope).
