# Auditline report

**Scope:** file `module_a.tsx`, `module_b.tsx`, `module_c.tsx`, `module_e.tsx`, `module_e.test.tsx` · **Mode:** full · **Languages:** typescript
**Tools:** eslint: ran (bundled fallback config) | tsc: ran (project tsconfig.json; no diagnostics kept, see JSON notes)
**Coverage:** all files in scope (`module_a.tsx` and `module_b.tsx`: no findings)

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 11 | 6 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.tsx:25` TS-SEC-02: Live translation API key hardcoded in client component

```tsx
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';
```

**Why:** A `tr_live_` credential is sent as a Bearer token from `translate()` in a browser component, so it sits in the repository, in git history and in the client bundle that every visitor downloads. Leak happens at commit, so reachability does not lower it (X-SEV-04).
**Fix:** Remove the literal and rotate the key. Call an own backend route (as `module_a.tsx` does with `/api/reviews/:id/translate`) that reads the key from an environment variable on the server.
**Cite:** CWE-798; CWE-200 (client bundle); OWASP A07:2021 Identification and Authentication Failures; OWASP Secrets Management Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_c.tsx:101` TS-SEC-16: Review text and translation output rendered as raw HTML

```tsx
dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
```

**Why:** `review.body` is written by any customer and `translated[...]` is third-party API output; both go into `__html` unsanitized for every visitor of the product page, so a review containing `<img src=x onerror=...>` runs script in other users' sessions (stored XSS, C1 x R1).
**Fix:** Render as text: `<div className="review__body">{translated[review.id] ?? review.body}</div>`. If HTML is required, pass it through `DOMPurify.sanitize`.
**Cite:** CWE-79; OWASP A03:2021 Injection; React docs, `dangerouslySetInnerHTML`
**Source:** eslint (react/no-danger) · confidence: high

### [blocker] `module_e.tsx:44` TS-SEC-04: Server action deletes a task by client-supplied id with no session or membership check

```tsx
const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
```

**Why:** `deleteTask` is a `'use server'` function, so it is a public POST endpoint. Unlike `updateTaskStatus` (which calls `requireProjectMember(projectId)` first), it never reads the session or checks membership: anyone who can call the action, signed in or not, can delete any task by uuid, in any project (C1 data loss, R1).
**Fix:** Load the task's `projectId` first, call `await requireProjectMember(projectId)`, then delete (or `deleteMany` scoped to the project the caller belongs to).
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; Next.js docs, "Data Security" (Server Actions are public endpoints)
**Source:** model · confidence: high

### [blocker] `module_e.tsx:49` TS-SEC-04: Module-level QueryClient shared across requests is dehydrated whole into every response

```tsx
const serverQueryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
```

**Why:** One `QueryClient` lives for the whole server process. `ProjectBoardPage` prefetches `['tasks', projectId]` into it and then `dehydrate(serverQueryClient)` (line 59) serializes the entire cache, so a member of project B receives the task lists of every project that was rendered earlier by anyone, and the 60 s `staleTime` serves cached tasks to later requests without a query (cross-user, cross-tenant exposure, C1 x R1; any user who is a member of any project reaches it).
**Fix:** Create the client inside the request: `const queryClient = new QueryClient(...)` in `ProjectBoardPage` (or a `cache()`d per-request factory) and dehydrate that one.
**Cite:** CWE-639; CWE-524; OWASP A01:2021 Broken Access Control; TanStack Query docs, "Advanced Server Rendering" (create a new QueryClient per request)
**Source:** model · confidence: high

### [major] `module_c.tsx:51` TS-ERR-11: Review load has no status check, no catch and no finally: spinner stays on forever

```tsx
const res = await fetch(`/api/products/${productId}/reviews`);
```

**Why:** `load()` runs `setLoading(true)`, then `fetch` and `res.json()` with no `res.ok` test and no `try/finally`; a 500, an HTML error page or a network error throws, the rejection is unhandled (eslint no-floating-promises at line 63) and `setLoading(false)` never runs, so the product page shows "Loading reviews..." forever. The same holds for the per-author fetch on line 55 (C2 x R1, main flow).
**Fix:** Wrap the body in `try { ... if (!res.ok) throw new Error(...) } catch (e) { setError(...) } finally { setLoading(false) }`, render a `role="alert"` error state, and check `authorRes.ok`; or move the fetch into `useQuery`.
**Cite:** WHATWG Fetch Standard (promise rejects only on network errors); React docs, "Synchronizing with Effects"; CWE-755; CWE-252
**Source:** model · confidence: high

### [major] `module_c.tsx:55` TS-PERF-01: One author request per review inside a loop (N+1)

```tsx
const authorRes = await fetch(`/api/users/${review.authorId}`);
```

**Why:** For each review the effect awaits a separate `/api/users/:id` call, one after another, so a product with 200 reviews makes 201 sequential round trips before anything renders (X-SEV-02; the review count is unbounded, request path, every visit). Tool: no-await-in-loop at lines 55-56, merged into this one finding.
**Fix:** Fetch the distinct author ids in one batched call (`/api/users?ids=...`, as `module_a.tsx` does) and join client-side.
**Cite:** CWE-1073; web.dev, "Avoid chaining critical requests"
**Source:** eslint (no-await-in-loop) · confidence: high

### [major] `module_c.tsx:64` TS-COR-11: Effect reads productId but has an empty dependency array, and no cleanup

```tsx
}, []);
```

**Why:** The effect fetches `/api/products/${productId}/reviews` once at mount. When the `productId` prop changes the component keeps showing the previous product's reviews and authors; the effect also has no abort or ignore flag, so with a changing id an older, slower response could overwrite a newer one (C2 x R1).
**Fix:** Depend on `[productId]`, add an `AbortController` or `ignore` flag in the cleanup, or use `useQuery` with the id in the query key.
**Cite:** React docs, "Synchronizing with Effects" and "Removing Effect Dependencies"
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_c.tsx:69` TS-COR-16: Translation cache keyed by review id only, ignores targetLanguage

```tsx
setTranslated((prev) => ({ ...prev, [review.id]: text }));
```

**Why:** `translated` is keyed by `review.id` but each value depends on `targetLanguage` as well. After the user switches language the old translation is still rendered (line 101 reads `translated[review.id]`), so a review shows Spanish text while French is selected; `module_a.tsx` keys by `reviewId:target` for this reason (C2 x R1, wrong visible data).
**Fix:** Key the cache by review id and target (`${review.id}:${targetLanguage}`) on both write and read.
**Cite:** TanStack Query docs, "Query Keys" (every input belongs in the key); CWE-524
**Source:** model · confidence: high

### [major] `module_e.test.tsx:10` TS-TEST-07: Membership mock always grants; no test proves a non-member is rejected

```tsx
membership: { findUnique: vi.fn(async () => ({ role: 'member' })) },
```

**Why:** The module-level factory makes `db.membership.findUnique` return a member for every test and no test overrides it to `null`, so every test passes with the authorization check in `requireProjectMember` deleted; the denied path (the behavior that matters) is untested (C2 x R1).
**Fix:** Add a test that sets `vi.mocked(db.membership.findUnique).mockResolvedValueOnce(null)` and expects the action or page to reject.
**Cite:** ISTQB Foundation syllabus, boundary value analysis; OWASP ASVS 4.0.3 V4.1 (access control must be verified to deny)
**Source:** model · confidence: high

### [major] `module_e.test.tsx:76` TS-TEST-02: `moves a task to done` asserts only that a mock exists

```tsx
expect(db.task.update).toBeDefined();
```

**Why:** `db.task.update` is a `vi.fn()` and is always defined, so the test passes whatever the board does; nothing checks that the select change produced a mutation or a cache update. It is the only test of the move path (C2 x R1, false confidence).
**Fix:** Assert on the outcome, for example `await waitFor(() => expect(screen.getByRole('heading', { name: 'Done (1)' })).toBeInTheDocument())` or `expect(db.task.update).toHaveBeenCalledWith(...)` through the action.
**Cite:** Jest/Vitest docs, `expect` matchers; Testing Library docs, "Guiding Principles"
**Source:** model · confidence: high

### [major] `module_e.tsx:6` TS-COR-74: Database client and server actions share a module with client components

```tsx
import { db } from '@/lib/db';
```

**Why:** This one file holds the `db` import, `'use server'` actions, an async server component (`ProjectBoardPage`) and hook-using client components (`TaskBoard`, `TaskSearch`, `UpdatedAgo`) with no `'use client'` boundary and no `import 'server-only'`. A client component cannot live in a server module and vice versa: marking the file `'use client'` pulls `@/lib/db` into the browser bundle, leaving it unmarked makes the hooks fail in the server environment. Assumption: the file is one Next.js App Router module, as the `'use server'` directives and `next/cache` import indicate.
**Fix:** Split the file: server module (`import 'server-only'`, actions, page) and a `'use client'` module for the board components that calls the actions or API routes.
**Cite:** Next.js docs, "Server and Client Components: Keeping server-only code out of the client environment"
**Source:** model · confidence: medium

### [major] `module_e.tsx:85` TS-COR-11: Interval effect captures the first updatedAt and never refreshes

```tsx
}, []);
```

**Why:** `UpdatedAgo` recomputes the label from `updatedAt` inside an interval created once with `[]`. When the task is updated and the `updatedAt` prop changes, the interval keeps formatting the old timestamp, so the card shows the previous "Updated 3 hours ago" until it unmounts (C2 x R1, wrong visible data; not self-correcting).
**Fix:** Add `updatedAt` to the dependency array (or derive the label in render from a ticking `now` state).
**Cite:** React docs, "Removing Effect Dependencies"
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_e.tsx:118` TS-COR-12: Search request has no abort or ignore flag: stale responses overwrite newer ones

```tsx
getTasks(projectId, term)
```

**Why:** Each keystroke starts a fetch in the effect and the `.then` sets `results` whatever order replies arrive in, so a slow response for "re" can land after the one for "release" and show the wrong list; the effect has no cleanup (C2 x R1).
**Fix:** Pass an `AbortSignal` from an `AbortController` aborted in the effect cleanup (or an `ignore` flag), or use `useQuery` with the term in the key.
**Cite:** React docs, "Synchronizing with Effects" (fetching data, race conditions); MDN, `AbortController`
**Source:** model · confidence: high

### [major] `module_e.tsx:138` TS-ERR-55: Optimistic status update has no rollback and no settle on error

```tsx
onMutate: async ({ taskId, status }) => {
```

**Why:** `onMutate` writes the new status into the cache, but there is no `onError` that restores the snapshot and `invalidateQueries` only runs in `onSuccess`. If `updateTaskStatus` rejects (for example the membership check throws), the card stays in the wrong column while the banner says the change was not saved, until something else refetches (C2 x R1).
**Fix:** Return `{ previous }` from `onMutate`, restore it in `onError`, and invalidate in `onSettled`.
**Cite:** TanStack Query docs, "Optimistic Updates"
**Source:** model · confidence: high

### [major] `module_e.tsx:167` TS-COR-13: Array index used as key for stateful task cards

```tsx
key={index}
```

**Why:** `TaskCard` holds `confirmingDelete` state and the list is filtered by status, so moving a task changes which card sits at each index; the "Confirm delete" state then attaches to a different task and one click deletes the wrong task (C2 x R1, wrong row).
**Fix:** Use `key={task.id}`.
**Cite:** React docs, "Rendering Lists" (keys)
**Source:** model · confidence: high

### [minor] `module_c.tsx:52` TS-MAINT-08: API responses cast with `as` instead of validated

```tsx
const list = (await res.json()) as Review[];
```

**Why:** `as Review[]` (and `as Author` on line 56, `as { translation: string }` on line 39) asserts the shape of untrusted JSON without checking it; a changed API field turns into `undefined` deep in render (for instance `review.author.avatarUrl`). `module_a.tsx` parses the same payloads with Zod.
**Fix:** Parse with a Zod schema at the boundary (`z.array(reviewSchema).parse(await res.json())`).
**Cite:** Zod docs, "Basic usage"; TypeScript handbook, "Type Assertions"
**Source:** model · confidence: high

### [minor] `module_c.tsx:59` TS-DIFF-01: console.log of the loaded reviews and authors on every page load

```tsx
console.log('reviews loaded', withAuthors);
```

**Why:** Debug output of the full review and author list runs on every visit to the product page; it bypasses any logger and dumps user-written text and author names into the browser console (C3 x R1, no secrets).
**Fix:** Delete it.
**Cite:** CWE-532; CWE-489 (active debug code)
**Source:** eslint (no-console) · confidence: high

### [minor] `module_c.tsx:103` TS-ACC-01: Translate control is a clickable div

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** A `div` with `onClick`, no role, no `tabIndex` and no key handler cannot be reached or activated from the keyboard (WCAG 2.1.1 Level A). It is a secondary per-review action, not the only way through a core flow, so minor (X-SEV-06). Lint also flags the Promise-returning handler (no-misused-promises) at the same line.
**Fix:** Use `<button type="button" onClick={() => void handleTranslate(review)}>Translate</button>`.
**Cite:** WCAG 2.2 SC 2.1.1 Keyboard (Level A); WAI-ARIA APG, "Button pattern"
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:43` TS-TEST-06: Focused test (`it.only`) committed

```tsx
it.only('renders one column per status', async () => {
```

**Why:** `.only` makes the runner execute this one test in the file and skip the four others, including the search and move tests. Vitest rejects `.only` when the `CI` environment variable is set (`allowOnly` defaults to `!process.env.CI`), so I assume CI fails the run and rate it minor; local runs are silently narrowed.
**Fix:** Remove `.only`.
**Cite:** Vitest docs, `allowOnly` and `test.only`
**Source:** model · confidence: medium

### [minor] `module_e.test.tsx:67` TS-TEST-09: `user.type` not awaited, so the assertion runs before typing happens

```tsx
user.type(search, 'login');
```

**Why:** The promise from `user.type` is dropped, so `expect(screen.queryByRole('alert')).not.toBeInTheDocument()` on the next line runs before any key is typed and passes whatever the search does; the test cannot fail on the behavior its name describes.
**Fix:** `await user.type(search, 'login');` then assert (preferably after `waitFor`).
**Cite:** user-event docs, "Introduction" (setup() and awaited calls)
**Source:** eslint (@typescript-eslint/no-floating-promises) · confidence: high

### [minor] `module_e.tsx:163` TS-COR-72: Number on the left of `&&` renders a stray 0

```tsx
{columnTasks.length && (
```

**Why:** For an empty column `columnTasks.length` is `0`, which React renders as the text "0" under the heading ("Done (0)" is followed by a bare 0) instead of nothing (C3 x R1).
**Fix:** Use `columnTasks.length > 0 && (...)` or a ternary.
**Cite:** React docs, "Conditional Rendering"
**Source:** eslint (react/jsx-no-leaked-render) · confidence: high

### [nit] 2 nits from eslint

Collapsed because eslint reports them (`no-unused-vars`: unused `useMemo` at `module_c.tsx:1`, unused `useCallback` at `module_e.tsx:1`). Remove the names from the imports.

## Questions

None.

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
