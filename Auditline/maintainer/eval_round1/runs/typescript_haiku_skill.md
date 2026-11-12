# Auditline report

**Scope:** file `module_a.tsx`, `module_b.tsx`, `module_c.tsx`, `module_e.tsx`, `module_e.test.tsx` · **Mode:** full · **Languages:** typescript
**Tools:** eslint: ran (bundled fallback config) · tsc: ran (project tsconfig.json)
**Coverage:** all 5 files in scope. Discarded tool results (react, @tanstack/react-query and zod not installed in the review environment) are listed in the JSON `tools[].note`.

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 7 | 8 | 3 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.tsx:25` TS-SEC-02: Live translation API key hardcoded in client-side code

```tsx
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';
```

**Why:** The key has a live prefix and line 32 sends it as a Bearer token from browser code, so every visitor's bundle contains it and can spend the provider account. Any visitor of a product page can read it (R1), so this is the X-SEV-04 class and is not downgraded. module_a.tsx already routes translation through /api/reviews/:id/translate, which is the pattern to follow.
**Fix:** Delete the literal, call a server route that reads the key from the environment (as translateReview in module_a.tsx does), and rotate the leaked key.
**Cite:** CWE-798; CWE-200; OWASP A07:2021 Identification and Authentication Failures
**Source:** model · confidence: high

### [blocker] `module_c.tsx:101` TS-SEC-16: Review text and translation rendered as raw HTML

```tsx
dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
```

**Why:** review.body is written by customers and the translation comes from a third party. Both reach innerHTML unescaped, so a review containing a script tag runs in every visitor's session (stored XSS, reachable by anyone who can post a review, R1). Blocker under X-SEV-04.
**Fix:** Render the text as a child instead: {translated[review.id] ?? review.body} inside the element. If HTML must be kept, sanitize it with DOMPurify first.
**Cite:** CWE-79; OWASP A03:2021 Injection; React docs, dangerouslySetInnerHTML
**Source:** eslint (react/no-danger) · confidence: high

### [blocker] `module_e.tsx:44` TS-SEC-04: deleteTask server action has no session or ownership check

```tsx
const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
```

**Why:** A 'use server' function is a public POST endpoint. deleteTask never reads the session and deletes by task id alone, so any signed-up user can delete any task in any project if they know its UUID. updateTaskStatus on line 34 runs requireProjectMember and this action does not (C1 data loss, R1).
**Fix:** Look up projectId first, call requireProjectMember(projectId), then delete. Or use deleteMany scoped to the session user's memberships.
**Cite:** CWE-862; CWE-639; OWASP A01:2021 Broken Access Control; Next.js docs, Data Security (Server Actions are public endpoints)
**Source:** model · confidence: high

### [blocker] `module_e.tsx:49` TS-SEC-04: Module-level QueryClient dehydrates other projects' tasks into every server page

```tsx
const serverQueryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
```

**Why:** The client is created once per server process and ProjectBoardPage prefetches each project's tasks into it. Line 59 calls dehydrate(serverQueryClient), which serializes the whole cache into every response. A member of project A therefore receives the task lists of every other project prefetched since the process started: cross-user data exposure (C1, R1). TS-COR-01 covers the per-request rule; it is filed here as security so a --security-only run keeps it.
**Fix:** Create the QueryClient inside ProjectBoardPage so each request dehydrates only its own prefetch.
**Cite:** CWE-488; CWE-639; TanStack Query docs, Advanced Server Rendering (one QueryClient per request)
**Source:** model · confidence: high

### [major] `module_c.tsx:55` TS-PERF-01: One request per review author, awaited in sequence

```tsx
const authorRes = await fetch(`/api/users/${review.authorId}`);
```

**Why:** Lines 55-56 await one request per review, so latency grows with the number of reviews a product has. That count is not bounded and grows over time (X-SEV-02, U3), and it sits on the product page (R1). module_a.tsx batches the same lookup into one request. Lint reports minor; raised to major for this consequence.
**Fix:** Collect the distinct authorIds, fetch them in one batched request as fetchReviews in module_a.tsx does, and join by id.
**Cite:** CWE-1073; web.dev, Avoid chaining critical requests
**Source:** eslint (no-await-in-loop) · confidence: high

### [major] `module_c.tsx:63` TS-COR-10: load() started without a catch; a failed request leaves the list stuck on loading

```tsx
load();
```

**Why:** load() is fire-and-forget and has no try/catch and no res.ok check. If the fetch fails or res.json() throws on an error page, the promise rejects unhandled, setLoading(false) never runs, and the visitor sees 'Loading reviews...' indefinitely. The product page is shown on every visit (R1), so major.
**Fix:** Wrap the body in try/catch/finally with an error state, check res.ok, and use TanStack Query as module_a.tsx does.
**Cite:** typescript-eslint, no-floating-promises; React docs, Synchronizing with Effects
**Source:** eslint (@typescript-eslint/no-floating-promises) · confidence: high

### [major] `module_c.tsx:64` TS-COR-11: Effect reads productId but depends on []; reviews stay stale when the product changes

```tsx
}, []);
```

**Why:** The effect calls load(), which reads productId, but the dependency list is empty. If the same mounted component is given another product, it keeps the previous product's reviews and fetches nothing. There is no ignore flag either, so an earlier response can overwrite a later one (TS-COR-12). Wrong data on a customer-facing screen (C2, R1).
**Fix:** List [productId] and ignore stale responses with a cleanup flag or AbortController, or key a useQuery on productId as module_a.tsx does.
**Cite:** React docs, Removing Effect Dependencies; React docs, Synchronizing with Effects
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_e.tsx:83` TS-COR-11: UpdatedAgo captures updatedAt once; its interval keeps the first timestamp

```tsx
const timer = window.setInterval(() => setLabel(formatAge(updatedAt)), 30_000);
```

**Why:** The interval closure reads updatedAt from the first render, and the dependency list on line 85 is empty. Cards are keyed by index (line 167), so when the data behind a card changes the same component keeps the old timestamp and shows a wrong age on the main board (C2, R1).
**Fix:** Put updatedAt in the dependency list, or compute the label in render and drop the interval state. Key the card by task id.
**Cite:** React docs, Removing Effect Dependencies; react-hooks/exhaustive-deps docs
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_e.tsx:140` TS-ERR-55: Optimistic status move is never rolled back when the save fails

```tsx
queryClient.setQueryData<Task[]>(tasksKey, (prev) => prev?.map((t) => (t.id === taskId ? { ...t, status } : t)));
```

**Why:** onMutate writes the new status into the cache. There is no onError that restores it, and onSuccess is the only invalidation. When updateTaskStatus rejects, the card stays in the new column while the banner says 'Your last change was not saved' (line 157). The UI keeps data the server refused (C2, R1).
**Fix:** Snapshot the list in onMutate and return it as context, restore it in onError, and invalidate in onSettled (the TS-ERR-55 CORRECT example).
**Cite:** TanStack Query docs, Optimistic Updates
**Source:** model · confidence: high

### [major] `module_e.tsx:167` TS-COR-13: Task cards keyed by array index while each card holds its own state

```tsx
key={index}
```

**Why:** TaskCard keeps confirmingDelete in state. When a card is moved away or removed, the card at the same index inherits the next task's state, so a 'Confirm delete' armed on one task can be clicked on another, and the wrong task is deleted (C2, R1). Lint reports minor; raised to major because the wrong task can be deleted.
**Fix:** Use key={task.id}.
**Cite:** React docs, Rendering Lists (keys); React docs, Preserving and Resetting State
**Source:** eslint (react/no-array-index-key) · confidence: high

### [major] `module_e.test.tsx:76` TS-TEST-02: Move-to-done test passes without checking the move

```tsx
expect(db.task.update).toBeDefined();
```

**Why:** The mock is always defined, so this passes whether or not the status change happens. It is the only test of the move flow and nothing it checks would fail if moveTask broke, so the coverage is removed (major under the tests ref).
**Fix:** Wait for the outcome the user sees (for example the 'Done (1)' heading), with the server action it calls mocked, instead of toBeDefined().
**Cite:** Testing Library, Guiding Principles; Vitest docs, expect
**Source:** model · confidence: high

### [minor] `module_b.tsx:46` TS-COR-04: Possibly undefined maximumFractionDigits used in arithmetic (tsc TS18048)

```tsx
return format.format(amountMinor / 10 ** digits);
```

**Why:** tsc reports TS18048 because digits is typed as possibly undefined. At runtime a currency format always resolves a digit count, so the amount is correct. The defect is a compile error under the project's strict tsconfig, which is why it is minor.
**Fix:** Default the digit count explicitly, for example `?? 2`, or use a table of ISO 4217 minor-unit exponents.
**Cite:** TypeScript handbook, Strict null checks; ECMA-402, Intl.NumberFormat resolvedOptions
**Source:** tsc (TS18048) · confidence: high

### [minor] `module_c.tsx:59` TS-DIFF-01: console.log runs on every product page load

```tsx
console.log('reviews loaded', withAuthors);
```

**Why:** The call runs on every product page view and prints the reviews, with author names and avatars, to the visitor's console. No secret is logged. Minor because it runs on every page load (X-SEV-07).
**Fix:** Delete the call.
**Cite:** CWE-532; OWASP Logging Cheat Sheet
**Source:** eslint (no-console) · confidence: high

### [minor] `module_c.tsx:103` TS-ACC-01: Translate control is a div with onClick, unreachable from the keyboard

```tsx
<div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** The only way to translate a review. A div with onClick has no role, no focus and no key handler, so keyboard and screen-reader users cannot reach it (WCAG 2.1.1, Level A). It is a secondary control, so minor under X-SEV-06. module_a.tsx uses a native button.
**Fix:** Use `<button type="button" className="review__translate" onClick={...}>Translate</button>`.
**Cite:** WCAG 2.2 SC 2.1.1 Keyboard (A); WAI-ARIA APG, Button pattern
**Source:** model · confidence: high

### [minor] `module_e.tsx:118` TS-COR-12: Search responses can arrive out of order and overwrite newer results

```tsx
getTasks(projectId, term)
```

**Why:** Every keystroke starts a request with no cancel or ignore flag, and .then always calls setResults. A slow response for an earlier term can land after a later one and show the wrong list. Minor: search is a secondary control, and the next keystroke issues a new request.
**Fix:** Abort the previous request in the effect cleanup (getTasks already takes a signal), or key a useQuery on term.
**Cite:** React docs, Synchronizing with Effects (cleanup and ignoring stale responses)
**Source:** model · confidence: medium

### [minor] `module_e.tsx:163` TS-COR-72: Empty column renders a stray 0

```tsx
{columnTasks.length && (
```

**Why:** When a column has no tasks, columnTasks.length is 0 and React renders it, so the column shows a bare 0 under its heading. Cosmetic on a visible screen (C3).
**Fix:** Compare explicitly: `{columnTasks.length > 0 && (`.
**Cite:** React docs, Conditional Rendering (do not put numbers on the left side of &&)
**Source:** eslint (react/jsx-no-leaked-render) · confidence: high

### [minor] `module_e.test.tsx:43` TS-TEST-06: it.only narrows the file to one test

```tsx
it.only('renders one column per status', async () => {
```

**Why:** With .only, the other three tests in this file are skipped. Vitest rejects .only when CI is set (allowOnly defaults to !process.env.CI), so CI is protected, but a local run silently executes one test.
**Fix:** Remove .only.
**Cite:** Vitest docs, allowOnly; Jest docs, test.only
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:53` TS-TEST-09: Card count asserted with a CSS class selector

```tsx
expect(container.querySelectorAll('.task-card')).toHaveLength(2);
```

**Why:** The test is coupled to a class name. A rename that changes nothing for users breaks it, and markup a screen reader cannot use still passes (C3).
**Fix:** Query by role, for example screen.getAllByRole('heading', { level: 3 }), and assert the count.
**Cite:** Testing Library, Guiding Principles and About Queries (getByRole first)
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:67` TS-TEST-09: user.type is not awaited, so the assertion runs before typing

```tsx
user.type(search, 'login');
```

**Why:** user-event calls are async. Without await the expectation runs before any keystroke, so the test passes whether or not the error alert appears while typing. The assertion checks nothing (minor under TS-TEST-09).
**Fix:** Write `await user.type(search, 'login');` and then assert.
**Cite:** user-event docs, Introduction (setup() and awaited calls)
**Source:** model · confidence: high

### [nit] `module_a.tsx:115` TS-ACC-09: aria-label on a span with no role is ignored

```tsx
<span className="review__rating" aria-label={`${review.rating} out of 5 stars`}>
```

**Why:** Naming is prohibited on generic elements, so the label is dropped and screen readers read the star glyphs instead. Nit: the rating is still visible.
**Fix:** Add role="img" to the span so the label is announced.
**Cite:** WAI-ARIA 1.2 (naming prohibited on generic)
**Source:** model · confidence: high

### [nit] 2 unused imports from eslint (no-unused-vars)

`module_c.tsx:1` imports an unused `useMemo`; `module_e.tsx:1` imports an unused `useCallback`. Run the fix by deleting both names from their import lines (TS6133 / no-unused-vars).

## Questions

None.

## Pre-existing (not part of this change)

None.
