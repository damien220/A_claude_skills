# Auditline report

**Scope:** file scope, five files (`module_a.tsx`, `module_b.tsx`, `module_c.tsx`, `module_e.tsx`, `module_e.test.tsx`), no git diff · **Mode:** full · **Languages:** typescript
**Tools:** eslint: ran (bundled fallback config) | tsc: ran (project tsconfig.json); results caused by uninstalled react, react-query and zod types were dropped (reasons in the JSON `tools` notes)
**Coverage:** all files in scope

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 10 | 10 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker to nit), then file, then line.

### [blocker] `module_c.tsx:25` TS-SEC-02: Live translation API key hardcoded in client code and sent as a Bearer token from the browser

```tsx
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';
```

**Why:** TRANSLATE_API_KEY is a live-prefixed credential (tr_live_...) used in the Authorization header at line 32 of a component module, so it ships in the JavaScript bundle to every visitor and stays in git history. Any anonymous visitor can read it and spend or abuse the translation account (C1 / R1: the leak happens at commit, D1-D3 never apply).
**Fix:** Remove the literal and rotate the key. Call an own backend route (as module_a.tsx does with /api/reviews/:id/translate) that reads the key from process.env on the server.
**Cite:** CWE-798; CWE-200 (secret in client bundle); OWASP A07:2021 Identification and Authentication Failures; Next.js docs, Environment Variables (values reachable from client code are inlined into the bundle)
**Source:** model · confidence: high

### [blocker] `module_c.tsx:101` TS-SEC-16: Review text and translation output rendered as raw HTML

```tsx
              dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
```

**Why:** review.body is written by other customers and the translation comes from a third-party API; both go into dangerouslySetInnerHTML, so a review containing <img src=x onerror=...> runs script in every visitor's session (stored XSS, C1 / R1, any signed-up user can post a review).
**Fix:** Render as text: <div className="review__body">{translated[review.id] ?? review.body}</div>. If markup is required, pass it through DOMPurify.sanitize and render the result unchanged.
**Cite:** CWE-79; OWASP A03:2021 Injection; React docs, dangerouslySetInnerHTML
**Source:** eslint (react/no-danger) · confidence: high

### [blocker] `module_e.tsx:44` TS-SEC-04: deleteTask deletes any task by id with no session or membership check

```tsx
  const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
```

**Why:** 'use server' functions are public POST endpoints. deleteTask validates only that taskId is a UUID, then deletes the row; unlike updateTaskStatus it never calls requireProjectMember, so any caller, signed in or not, who learns or guesses a task id (ids appear in the page and in the API) can delete another project's tasks (C1 / R1).
**Fix:** Load the task's projectId, call await requireProjectMember(projectId) before the delete (as updateTaskStatus does), or delete with a where clause scoped to the session's memberships and return 404 on a miss.
**Cite:** CWE-862; CWE-639; OWASP A01:2021 Broken Access Control; Next.js docs, Data Security (Server Actions are public endpoints)
**Source:** model · confidence: high

### [blocker] `module_e.tsx:49` TS-SEC-04: Module-level QueryClient on the server is shared by every request and dehydrated whole into each page

```tsx
const serverQueryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
```

**Why:** serverQueryClient lives for the life of the server process. ProjectBoardPage prefetches ['tasks', projectId] into it and then calls dehydrate(serverQueryClient) (line 59), which serializes every query cached so far, for every project. Any member of any project therefore receives the task titles of all projects viewed earlier by anyone (C1 cross-tenant data exposure / R1: membership of one project is enough); the 60 s staleTime also serves stale copies.
**Fix:** Create the client inside the request: `const queryClient = new QueryClient(...)` inside ProjectBoardPage (or a per-request cache() helper), prefetch into it and dehydrate that instance.
**Cite:** TanStack Query docs, Advanced Server Rendering (create the QueryClient per request to avoid sharing data between users); CWE-488; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [major] `module_c.tsx:51` TS-ERR-11: Reviews load has no status check and no error path: a failed request leaves the spinner on or breaks the page

```tsx
      const res = await fetch(`/api/products/${productId}/reviews`);
```

**Why:** load() calls fetch without checking res.ok, parses the body with an unchecked cast, and never clears the loading state if fetch or json throws (setLoading(false) at line 61 is skipped). The call at line 63 is a floating promise (ESLint no-floating-promises), so the rejection is unhandled and the user sees 'Loading reviews...' forever on any 500 or network error. This is the main content of the component (C2 / R1).
**Fix:** Wrap the body in try / catch / finally, throw on !res.ok, set an error state rendered with role="alert", and move setLoading(false) into finally; or use useQuery, which provides isPending and isError.
**Cite:** WHATWG Fetch Standard (the promise rejects only on network errors); React docs, Catching rendering errors with an error boundary (async errors are not caught); CWE-755; CWE-252
**Source:** model · confidence: high

### [major] `module_c.tsx:55` TS-PERF-01: One author request per review inside a sequential loop (N+1)

```tsx
        const authorRes = await fetch(`/api/users/${review.authorId}`);
```

**Why:** Each review triggers its own awaited fetch for the author, one after another, so latency grows linearly with the number of reviews of a product, which is not bounded (C2 / R1, X-SEV-02). A product with 200 reviews makes 201 sequential round trips before anything renders.
**Fix:** Batch the author lookup the way module_a.tsx does (one /api/users?ids=a,b,c request for the distinct authorId values) or fetch the authors with Promise.all over a bounded set.
**Cite:** CWE-1073; web.dev, Avoid chaining critical requests
**Source:** eslint (no-await-in-loop) · confidence: high

### [major] `module_c.tsx:64` TS-COR-11: Effect reads productId but declares no dependencies, so reviews of the previous product stay on screen

```tsx
  }, []);
```

**Why:** The effect closes over productId and has an empty dependency array, so when the parent passes a different productId the component keeps showing the first product's reviews (and has no abort or ignore flag for in-flight responses). Reachable by every navigation between products that reuses the component (C2 / R1).
**Fix:** Add productId to the dependency array, return a cleanup that aborts the request (AbortController) or sets an ignore flag, or move the fetch to useQuery with ['product-reviews', productId] as module_a.tsx does.
**Cite:** React docs, Synchronizing with Effects; React docs, Removing Effect Dependencies
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_c.tsx:69` TS-COR-16: Translation cache keyed by review id only, so a language change keeps showing the old language

```tsx
      setTranslated((prev) => ({ ...prev, [review.id]: text }));
```

**Why:** translated is keyed by review.id while the text depends on targetLanguage too. After a reader translates a review to French and then switches targetLanguage to German, line 101 still reads translated[review.id] and shows the French text, and the button gives no sign that the result is stale (C2 / R1: wrong locale served). module_a.tsx avoids this with translationKey(reviewId, target).
**Fix:** Key the entry by review id and target language (for example `${review.id}:${targetLanguage}`) both when writing here and when reading at line 101, or clear translated when targetLanguage changes.
**Cite:** TanStack Query docs, Query Keys (the key must include every input the result depends on); React docs, Choosing the State Structure
**Source:** model · confidence: high

### [major] `module_e.test.tsx:10` TS-TEST-07: Membership check is mocked to always allow and no test proves a rejection

```tsx
    membership: { findUnique: vi.fn(async () => ({ role: 'member' })) },
```

**Why:** The only test file for module_e.tsx (no other test file exists in the project) stubs db.membership.findUnique to return a member and never exercises the denied path of requireProjectMember, nor deleteTask at all, so the missing check in deleteTask (module_e.tsx:44) and any regression in the membership gate pass the suite (C2 / R1; assumes no other test file covers these actions).
**Fix:** Add table cases for member / non-member / no session on updateTaskStatus and deleteTask that expect a rejection and no db.task.update or db.task.delete call.
**Cite:** OWASP ASVS 4.0.3 V4.1 (verify that access control denies); ISTQB Foundation syllabus, boundary value analysis
**Source:** model · confidence: medium

### [major] `module_e.test.tsx:76` TS-TEST-02: 'moves a task to done' asserts only that a mock is defined

```tsx
    expect(db.task.update).toBeDefined();
```

**Why:** expect(db.task.update).toBeDefined() is true for any vi.fn(), so the test passes whether or not the status change is sent, whether the board updates, and whether the server action authorizes the caller. It is the only test of the move-task flow (optimistic update plus a persisted write), which would survive deleting the whole mutation (C2 / R1: false confidence).
**Fix:** Assert the outcome: await waitFor(() => expect(db.task.update).toHaveBeenCalledWith(expect.objectContaining({ data: { status: 'done' } }))) and that the 'Done (1)' heading appears.
**Cite:** Jest docs, expect (toBeDefined); Testing Library docs, Guiding Principles (test what the user observes)
**Source:** model · confidence: high

### [major] `module_e.tsx:85` TS-COR-11: Interval effect closes over updatedAt but has an empty dependency array, so the age label goes stale

```tsx
  }, []);
```

**Why:** The interval callback keeps the updatedAt from the first render. When a task is updated (status move, invalidate and refetch) or the card is reused for another task, the label keeps computing the age of the old timestamp, e.g. 'Updated 3 hours ago' on a task changed a minute ago (C2 / R1).
**Fix:** Add updatedAt to the dependency array (the effect restarts the interval and should also call setLabel(formatAge(updatedAt)) immediately), or derive the label from a shared clock in render.
**Cite:** React docs, Removing Effect Dependencies; React docs, Synchronizing with Effects
**Source:** eslint (react-hooks/exhaustive-deps) · confidence: high

### [major] `module_e.tsx:118` TS-COR-12: Search requests are not cancelled or ordered, so a slow earlier response overwrites a newer one

```tsx
    getTasks(projectId, term)
      .then((found) => { setSearchFailed(false); setResults(found); })
      .catch(() => setSearchFailed(true));
```

**Why:** Each change of term starts getTasks with no AbortSignal and no ignore flag, and the effect returns no cleanup. Responses can arrive out of order ('re' resolving after 'release'), so the visible results, and the searchFailed flag, can belong to an older term than the one in the input (C2 / R1).
**Fix:** Create an AbortController per effect run, pass its signal to getTasks (which already accepts one), return () => controller.abort(), and ignore AbortError in the catch; or use useQuery with ['tasks', projectId, 'search', term].
**Cite:** React docs, Synchronizing with Effects (fetching data, race conditions, cleanup); MDN, AbortController; CWE-772
**Source:** model · confidence: high

### [major] `module_e.tsx:138` TS-ERR-55: Optimistic status move has no rollback and only refetches on success

```tsx
    onMutate: async ({ taskId, status }) => {
      await queryClient.cancelQueries({ queryKey: tasksKey });
      queryClient.setQueryData<Task[]>(tasksKey, (prev) => prev?.map((t) => (t.id === taskId ? { ...t, status } : t)));
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tasksKey }),
```

**Why:** onMutate writes the new status into the cache and returns nothing, there is no onError to restore the previous list, and invalidation runs only in onSuccess. When updateTaskStatus rejects (non-member, deleted task, network error) the board keeps showing the task in the wrong column until the next unrelated refetch; the 'not saved' banner appears next to data that looks saved (C2 / R1).
**Fix:** Snapshot with getQueryData in onMutate and return it as context, restore it in onError, and move the invalidation to onSettled (module_b.tsx's star mutation shows the pattern).
**Cite:** TanStack Query docs, Optimistic Updates
**Source:** model · confidence: high

### [major] `module_e.tsx:167` TS-COR-13: Task cards keyed by array index while each card holds its own state

```tsx
                    key={index}
```

**Why:** Cards in a column are keyed by position. TaskCard keeps confirmingDelete and UpdatedAgo keeps label in local state, and the list shifts whenever a task is moved to another column (the optimistic update at line 140 removes it from this column at once): the next card inherits the 'Confirm delete' state, so one click on the button deletes a different task than the one the user clicked Delete on (C2 / R1, destructive wrong-row action).
**Fix:** Use the stable id: key={task.id}.
**Cite:** React docs, Rendering Lists (keys); React docs, Preserving and Resetting State
**Source:** eslint (react/no-array-index-key) · confidence: high

### [minor] `module_a.tsx:115` TS-ACC-09: aria-label on a role-less span whose visible content is only star glyphs

```tsx
              <span className="review__rating" aria-label={`${review.rating} out of 5 stars`}>
```

**Why:** Naming is prohibited on generic elements, so most screen readers ignore the label and announce the repeated star glyphs (or nothing), and the rating is not conveyed (C3).
**Fix:** Add role="img" to the span, or render visible text such as '4 out of 5' with the stars aria-hidden.
**Cite:** WAI-ARIA 1.2, naming prohibited on generic; WCAG 2.2 SC 1.1.1 Non-text Content (A)
**Source:** model · confidence: medium

### [minor] `module_b.tsx:46` TS-COR-04: resolvedOptions().maximumFractionDigits is number | undefined and is used in arithmetic

```tsx
  return format.format(amountMinor / 10 ** digits);
```

**Why:** tsc TS18048: 'digits' is possibly 'undefined', so the file does not pass the project's strict type check and the type-check gate fails. At runtime a currency-style NumberFormat always reports a number, so no wrong amount results (C3).
**Fix:** Default it explicitly: const digits = format.resolvedOptions().maximumFractionDigits ?? 2;
**Cite:** TypeScript docs, TSConfig Reference: strict (strictNullChecks); MDN, Intl.NumberFormat.prototype.resolvedOptions
**Source:** tsc (TS18048) · confidence: high

### [minor] `module_c.tsx:52` TS-MAINT-08: API responses cast with `as` instead of validated, at three boundaries

```tsx
      const list = (await res.json()) as Review[];
```

**Why:** res.json() results are asserted as Review[] here, as Author at line 56 and as { translation: string } at line 39, so a missing author, a renamed field or an error body flows through the component as if it matched the type, and the crashes appear later at review.author.avatarUrl (C3). module_a.tsx validates the same payloads with zod.
**Fix:** Parse each response with a zod schema (schema.parse or safeParse inside the fetch helper) and derive the type with z.infer.
**Cite:** TypeScript handbook, Type Assertions (an assertion is not a runtime check); Zod docs, Basic usage
**Source:** model · confidence: high

### [minor] `module_c.tsx:59` TS-DIFF-01: console.log dumps every loaded review and author on each page load

```tsx
      console.log('reviews loaded', withAuthors);
```

**Why:** The call runs every time the reviews load and writes all review bodies and author display names to the browser console, bypassing any logger and redaction (C3 / R1; minor on a request path, X-SEV-07). It holds no credentials, so it is not major.
**Fix:** Delete it, or use the project logger at debug level with identifiers only.
**Cite:** CWE-532; CWE-489
**Source:** eslint (no-console) · confidence: high

### [minor] `module_c.tsx:92` TS-ACC-09: aria-label on a role-less span whose visible content is only star glyphs

```tsx
              <span className="review__rating" aria-label={`${review.rating} out of 5 stars`}>
```

**Why:** Naming is prohibited on generic elements, so most screen readers ignore the label and announce the repeated star glyphs (or nothing), and the rating is not conveyed (C3). The same pattern is in module_a.tsx line 115.
**Fix:** Add role="img" to the span (keeping the aria-label), or render the rating as visible text such as '4 out of 5' with the stars aria-hidden.
**Cite:** WAI-ARIA 1.2, naming prohibited on generic; WCAG 2.2 SC 1.1.1 Non-text Content (A)
**Source:** model · confidence: medium

### [minor] `module_c.tsx:103` TS-ACC-01: Translate control is a div with a click handler: not focusable, not operable by keyboard

```tsx
            <div className="review__translate" onClick={() => handleTranslate(review)}>
```

**Why:** The div has no role, tabIndex or key handler, so keyboard and screen-reader users cannot reach or activate Translate. It is a secondary control (reading the review still works), so minor per X-SEV-06 (C3 / R1).
**Fix:** Use a native button: <button type="button" className="review__translate" onClick={() => handleTranslate(review)}>Translate</button> (module_a.tsx does this).
**Cite:** WCAG 2.2 SC 2.1.1 Keyboard (Level A); WAI-ARIA APG, Button pattern
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:43` TS-TEST-06: it.only narrows the file to one test

```tsx
  it.only('renders one column per status', async () => {
```

**Why:** While it.only is present the other four tests in the file do not run locally. The file uses Vitest, which rejects .only when the CI environment variable is set (allowOnly defaults to !process.env.CI), so CI is not narrowed, which is why this is minor; assumes the project does not set allowOnly: true.
**Fix:** Remove .only.
**Cite:** Vitest docs, allowOnly; Jest docs, test.only
**Source:** model · confidence: medium

### [minor] `module_e.test.tsx:53` TS-TEST-09: Card count asserted through a CSS class on the container

```tsx
    expect(container.querySelectorAll('.task-card')).toHaveLength(2);
```

**Why:** container.querySelectorAll('.task-card') couples the test to markup that users never see, and it passes on cards a keyboard or screen-reader user cannot operate (C3).
**Fix:** Assert by role or text: expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(2).
**Cite:** Testing Library docs, Guiding Principles and About Queries (getByRole first)
**Source:** model · confidence: high

### [minor] `module_e.test.tsx:67` TS-TEST-02: user.type is not awaited, so the assertion runs before anything is typed and cannot fail

```tsx
    user.type(search, 'login');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
```

**Why:** The test claims 'does not show an error while typing a search' but checks queryByRole('alert') immediately, before the typing, the debounce-free effect and the fetch have run, so it passes even if every search showed the error banner (C3 / R1; minor because it is not the only test of money, auth or persistence logic).
**Fix:** await user.type(search, 'login'), then await waitFor/findBy for the results list and assert the alert is absent.
**Cite:** user-event docs, Introduction (calls are async); Testing Library docs, About Queries (findBy for async results)
**Source:** model · confidence: high

### [minor] `module_e.tsx:163` TS-COR-72: {columnTasks.length && ...} renders a literal 0 in an empty column

```tsx
            {columnTasks.length && (
```

**Why:** When a column has no tasks, columnTasks.length is 0 and React renders the number 0 under the column heading (C3 / R1). The heading already shows the count, so the stray 0 is noise rather than a misread value.
**Fix:** Use a boolean condition: {columnTasks.length > 0 && (...)}.
**Cite:** React docs, Conditional Rendering (do not put numbers on the left side of &&)
**Source:** eslint (react/jsx-no-leaked-render) · confidence: high

### [nit] 2 unused-import nits

Collapsed because eslint reports them (`no-unused-vars`): `module_c.tsx:1`, `module_e.tsx:1`. Run `eslint --fix` after removing the names.

## Questions

Questions do not change the verdict.

- `module_e.tsx:132` — TaskBoard, TaskSearch and UpdatedAgo use hooks and TaskBoard is imported by the test, but the file has no 'use client' directive while it also imports '@/lib/db', '@/lib/auth' and 'next/cache' and defines async server components. Is this one file split into server and client modules in the real project? If it ships as one module it either fails to build as a Server Component or, with 'use client' added, bundles the database client into the browser (TS-COR-74).

