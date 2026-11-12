# Auditline report

**Scope:** files `module_a.tsx`, `module_b.tsx`, `module_c.tsx`, `module_e.tsx`, `module_e.test.tsx` · **Mode:** full · **Languages:** typescript
**Tools:** eslint: ran (bundled fallback config) | tsc: ran (project tsconfig.json)
**Coverage:** all files in scope

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 10 | 7 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.tsx:25` TS-SEC-02: Live translation API key hardcoded in a client component

```tsx
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';
```

**Why:** C1: a `tr_live_` credential is sent as a Bearer token (line 32) from browser code, so it ships in the JS bundle to every visitor and stays in git history. R1: anyone loading the product page can read it. X-SEV-04: never downgraded.
**Fix:** Remove the literal, rotate the key, and call an own backend route (e.g. POST /api/reviews/:id/translate) that reads the key from a server-side env var.
**Cite:** CWE-798; CWE-200; OWASP A07:2021 Identification and Authentication Failures; Next.js docs, Environment Variables
**Source:** model · confidence: high

### [blocker] `module_c.tsx:101` TS-SEC-16: Review body and third-party translation rendered as raw HTML

```tsx
dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
```

**Why:** C1 stored XSS: `review.body` is text written by any reviewer and `translated[...]` is third-party API output; both reach dangerouslySetInnerHTML unsanitized, so `<img src=x onerror=...>` in a review runs in every visitor's session. R1: anyone who can post a review. X-SEV-04.
**Fix:** Render as text: `<p className="review__body">{translated[key] ?? review.body}</p>`; if HTML is required, `DOMPurify.sanitize(...)` unchanged.
**Cite:** CWE-79; OWASP A03:2021 Injection; React docs, dangerouslySetInnerHTML
**Source:** eslint (react/no-danger) · confidence: high

### [blocker] `module_e.tsx:44` TS-SEC-04: deleteTask server action deletes any task by id with no session or membership check

```tsx
const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
```

**Why:** C1: 'use server' functions are public POST endpoints; unlike updateTaskStatus (line 34) this action never calls requireProjectMember, so any caller (even unauthenticated) who knows or obtains a task UUID deletes it from any project. R1.
**Fix:** Load the task's projectId first, `await requireProjectMember(projectId)`, then delete (or `deleteMany({ where: { id, project: { members: { some: { userId } } } } })`).
**Cite:** CWE-862; CWE-639; OWASP A01:2021 Broken Access Control; Next.js docs, Data Security (Server Actions are public endpoints)
**Source:** model · confidence: high

### [blocker] `module_e.tsx:49` TS-SEC-04: Module-level QueryClient on the server shares other projects' tasks across requests

```tsx
const serverQueryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
```

**Why:** C1: serverQueryClient lives for the whole server process; each ProjectBoardPage render prefetches ['tasks', projectId] into it (staleTime 60s) and `dehydrate(serverQueryClient)` serializes every cached query into the HTML, so a member of project A receives project B's tasks fetched for another user. R1: every page load.
**Fix:** Create the client per request: `const queryClient = new QueryClient(...)` inside ProjectBoardPage and dehydrate that one.
**Cite:** CWE-488; OWASP A01:2021 Broken Access Control; TanStack Query docs, Advanced Server Rendering (create the QueryClient per request)
**Source:** model · confidence: high

### [major] `module_c.tsx:55` TS-PERF-01: One /api/users request per review, awaited sequentially

```tsx
const authorRes = await fetch(`/api/users/${review.authorId}`);
const author = (await authorRes.json()) as Author;
```

**Why:** C2: n+1 sequential round trips before anything renders; reviews per product are unbounded (data-controlled), so a product with 200 reviews waits for 201 requests. R1: every product page load.
**Fix:** Fetch authors in one batched call: `/api/users?ids=${[...new Set(list.map(r => r.authorId))].map(encodeURIComponent).join(',')}`, or a reviews endpoint that embeds the author.
**Cite:** CWE-1073; web.dev, Avoid chaining critical requests
**Source:** eslint (no-await-in-loop) · confidence: high

### [major] `module_c.tsx:63` TS-ERR-11: Review load has no error path: a failed fetch leaves the spinner forever

```tsx
load();
```

**Why:** C2: load() is fire-and-forget with no try/catch/finally and no res.ok check (lines 51, 55); any network error, non-JSON 500 page or failed author lookup rejects, setLoading(false) never runs and the user sees 'Loading reviews…' forever with an unhandled rejection. R1: main content of the component.
**Fix:** Wrap in try/catch/finally, check `res.ok` for both fetches, keep an error state rendered with role="alert", and `void load()` or use useQuery (isError).
**Cite:** React docs, error boundaries do not catch async errors; WHATWG Fetch Standard (rejects only on network errors); CWE-755
**Source:** eslint (@typescript-eslint/no-floating-promises) · confidence: high

### [major] `module_c.tsx:64` TS-COR-11: Effect fetches reviews for productId but has an empty dependency array

```tsx
}, []);
```

**Why:** C2: when productId changes (client navigation between products reusing the component) the previous product's reviews stay on screen. R1: ordinary navigation.
**Fix:** Depend on `[productId]` and guard with an ignore flag or AbortController in the cleanup (TS-COR-12) so a slow earlier response cannot overwrite the newer one.
**Cite:** React docs, Synchronizing with Effects; React docs, Removing Effect Dependencies
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_c.tsx:69` TS-COR-16: Translation cache keyed by review id only, not by target language

```tsx
setTranslated((prev) => ({ ...prev, [review.id]: text }));
```

**Why:** C2: the translated text depends on targetLanguage but is stored under `review.id`; after the user switches language, line 101 keeps showing the old language's translation for every review already translated. R1: any language switch.
**Fix:** Key by both inputs, e.g. `${review.id}:${targetLanguage}`, and read with the same key.
**Cite:** TanStack Query docs, Query Keys (include every variable the result depends on); CWE-524
**Source:** model · confidence: high

### [major] `module_e.test.tsx:10` TS-TEST-07: Membership mock always grants and no test proves a non-member is rejected

```tsx
membership: { findUnique: vi.fn(async () => ({ role: 'member' })) },
```

**Why:** C2: findUnique always resolves to a membership and no test overrides it to null, so every test passes with requireProjectMember deleted; the authorization path of updateTaskStatus (and the missing check in deleteTask) is never tested for denial. Reachability from the code under test: the open server actions (R1).
**Fix:** Add tests that `vi.mocked(db.membership.findUnique).mockResolvedValueOnce(null)` and expect the move/delete to fail (error alert shown, db.task.update/delete not called).
**Cite:** OWASP ASVS 4.0.3 V4.1 (verify access control denies); Vitest docs, vi.mocked / mockResolvedValueOnce
**Source:** model · confidence: high

### [major] `module_e.test.tsx:76` TS-TEST-02: 'moves a task to done' asserts only that the mock exists

```tsx
expect(db.task.update).toBeDefined();
```

**Why:** C2: `db.task.update` is a vi.fn() and is always defined, so the test passes whether the move succeeds, fails or never calls the server (findUniqueOrThrow returns undefined here, so the action actually throws). It is the only test of the status-change persistence path. R1.
**Fix:** Mock findUniqueOrThrow/update to return rows and assert `expect(db.task.update).toHaveBeenCalledWith({ where: { id: TASKS[0].id }, data: { status: 'done' } })` plus the card appearing under 'Done (1)'.
**Cite:** Vitest docs, expect / toHaveBeenCalledWith; Jest docs, Expect
**Source:** model · confidence: high

### [major] `module_e.tsx:6` TS-COR-74: Database client and server actions share a module with client components

```tsx
import { db } from '@/lib/db';
```

**Why:** C2: the file imports @/lib/db, @/lib/auth and next/cache and defines 'use server' actions and an async server component, yet TaskBoard/TaskSearch use useState/useEffect/useQuery (client-only). Without a server/client split it either fails the Next.js build or, if marked 'use client', pulls the db client into the browser bundle. Assumes a Next.js App Router project, as next/cache and 'use server' show. R1: whole board.
**Fix:** Move requireProjectMember, the actions (with a file-level 'use server') and ProjectBoardPage into server modules that `import 'server-only'`; put TaskBoard and children in a 'use client' file that imports only the actions.
**Cite:** Next.js docs, Server and Client Components: Keeping server-only code out of the client environment
**Source:** model · confidence: medium

### [major] `module_e.tsx:118` TS-COR-12: Search fetch per keystroke with no abort or ignore flag: older results overwrite newer

```tsx
getTasks(projectId, term)
  .then((found) => { setSearchFailed(false); setResults(found); })
  .catch(() => setSearchFailed(true));
```

**Why:** C2: each keystroke starts a request and none is cancelled; when 'rel' resolves after 'release', the list shows results for the stale term. R1: ordinary typing.
**Fix:** Create an AbortController per effect run, pass its signal to getTasks, abort in the cleanup and ignore AbortError (or use useQuery keyed by the debounced term).
**Cite:** React docs, Synchronizing with Effects (fetching data, cleanup); MDN, AbortController
**Source:** model · confidence: high

### [major] `module_e.tsx:138` TS-ERR-55: Optimistic task move has no rollback on error and no settle invalidation

```tsx
onMutate: async ({ taskId, status }) => {
```

**Why:** C2: onMutate writes the new status into the cache but saves no snapshot, there is no onError restore and invalidation runs only onSuccess; when the server action rejects (not a member, deleted task) the card stays in the new column until a later refetch while the user believes it moved. R1: every move.
**Fix:** Snapshot with getQueryData in onMutate and return it, restore it in onError, and move the invalidateQueries call to onSettled.
**Cite:** TanStack Query docs, Optimistic Updates
**Source:** model · confidence: high

### [major] `module_e.tsx:167` TS-COR-13: TaskCard keyed by index although cards hold confirm-delete state and the list changes

```tsx
key={index}
```

**Why:** C2: TaskCard keeps confirmingDelete in state; after a task leaves the column (moved or deleted) the next task takes its index and inherits 'Confirm delete', so one click deletes the wrong task. R1: normal board use.
**Fix:** Use the stable id: `key={task.id}`.
**Cite:** React docs, Rendering Lists (keys must be stable); CWE-837
**Source:** eslint (react/no-array-index-key) · confidence: high

### [minor] `module_c.tsx:59` TS-DIFF-01: console.log of every loaded review on each page load

```tsx
console.log('reviews loaded', withAuthors);
```

**Why:** C3: unleveled debug output with review and author objects on every product page view, bypassing any logger; no secrets or PII beyond public display names. R1, so minor (X-SEV-07).
**Fix:** Delete it, or use the app's logger at debug level.
**Cite:** CWE-532; OWASP Logging Cheat Sheet
**Source:** eslint (no-console) · confidence: high

### [minor] `module_c.tsx:103` TS-ACC-01: Translate is a clickable div with no role, focus or key handler

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** C3: keyboard and screen-reader users cannot reach or activate Translate, a secondary control (X-SEV-06 minor). R1.
**Fix:** `<button type="button" className="review__translate" onClick={() => void handleTranslate(review)}>Translate</button>`
**Cite:** WCAG 2.2 SC 2.1.1 Keyboard (Level A); WAI-ARIA APG, Button pattern
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:43` TS-TEST-06: it.only committed: the other four TaskBoard tests are skipped locally

```tsx
it.only('renders one column per status', async () => {
```

**Why:** C2 on coverage: running the file locally executes only this test. Vitest rejects .only when CI is set (allowOnly defaults to !process.env.CI), so CI fails rather than silently narrowing; minor per the TEST-06 rule.
**Fix:** Remove `.only`.
**Cite:** Vitest docs, allowOnly; Jest docs, test.only
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:53` TS-TEST-09: Test counts cards through container.querySelectorAll on a CSS class

```tsx
expect(container.querySelectorAll('.task-card')).toHaveLength(2);
```

**Why:** C3: couples the test to markup (`.task-card`) rather than what users see; a class rename breaks it and it passes on inaccessible markup.
**Fix:** `expect(screen.getAllByRole('listitem', { name: … }))` or `within(column).getAllByRole('heading', { level: 3 })`.
**Cite:** Testing Library docs, Guiding Principles and About Queries (prefer getByRole)
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:67` TS-TEST-02: user.type is not awaited, so the assertion runs before any typing

```tsx
user.type(search, 'login');
```

**Why:** C3: the expect at line 68 runs synchronously before the first keystroke or search request, so 'no error while typing' passes whatever the search does (vacuous). Not the only search test, so minor.
**Fix:** `await user.type(search, 'login');` then `await waitFor(...)` or assert after the results appear.
**Cite:** user-event docs, Introduction (await every call); Testing Library docs, Async methods
**Source:** eslint (@typescript-eslint/no-floating-promises) · confidence: high

### [minor] `module_e.tsx:85` TS-COR-11: UpdatedAgo interval captures updatedAt at mount

```tsx
}, []);
```

**Why:** C3: the effect has [] deps and the label is initialised once, so when the card receives a different task or a new updatedAt (index keys at line 167, refetch after a move) the 'Updated …' label keeps describing the old timestamp. Display-only, so minor. R1.
**Fix:** Add `updatedAt` to the dependency array and recompute the label immediately in the effect (or derive the label in render from a ticking `now`).
**Cite:** React docs, Synchronizing with Effects; React docs, Removing Effect Dependencies
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: medium

### [minor] `module_e.tsx:163` TS-COR-72: `columnTasks.length &&` renders a stray 0 in empty columns

```tsx
{columnTasks.length && (
```

**Why:** C3: React renders the number 0, so every empty column (e.g. 'Done (0)') shows a bare '0' under its heading. R1: the default empty board state.
**Fix:** `{columnTasks.length > 0 && (` …
**Cite:** React docs, Conditional Rendering (do not put numbers on the left side of &&)
**Source:** eslint (react/jsx-no-leaked-render) · confidence: high

### [nit] 2 nits from eslint

Collapsed because eslint reports them (`no-unused-vars`, TS-MAINT-01: unused imports at `module_c.tsx:1`, `module_e.tsx:1`). Run `eslint --fix` or remove the imports.

## Questions

- `module_e.tsx:33` — updateTaskStatus loads the task with findUniqueOrThrow before the membership check, so a non-member gets a different error for an existing vs a missing task id. Are these errors surfaced to the client differently? If so, task ids can be probed (CWE-204).

## Pre-existing (not part of this change)

None (file scope).
