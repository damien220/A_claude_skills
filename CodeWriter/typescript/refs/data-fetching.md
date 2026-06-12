# Data Fetching — TypeScript Frontend Reference

Grounded in the **TanStack Query v5 docs**, **TkDodo's blog** (Practical React Query series),
and the **React docs** (Suspense). For the server-side half (RSC prefetch + hydration) see
`refs/nextjs-and-ssr.md`.

---

## `useEffect` data fetching is forbidden in new code

The hand-rolled Effect version has no cache, no deduplication, a race condition on fast
re-renders, no retry, and re-implements loading/error state per call site. (Source: react.dev —
"You Might Not Need an Effect"; TkDodo — "Why You Want React Query".)

```tsx
// WRONG — race condition: slow response for "ann" can overwrite fast response for "anna"
const [users, setUsers] = useState<User[]>([]);
const [loading, setLoading] = useState(false);
useEffect(() => {
  setLoading(true);
  fetch(`/api/users?q=${query}`)
    .then((r) => r.json())
    .then(setUsers)
    .finally(() => setLoading(false));
}, [query]);
```

```tsx
// CORRECT — cached, deduplicated, race-free, retried, observable
const { data: users, isPending, isError } = useQuery({
  queryKey: ['users', { q: query }],
  queryFn: ({ signal }) => fetchUsers(query, signal),   // signal: auto-abort on key change
});
```

---

## `queryKey` — the cache identity

Every parameter the `queryFn` depends on goes in the key. A param missing from the key means
two different requests share one cache entry. (Source: TkDodo — "Effective React Query Keys".)

```ts
// WRONG — page changes don't refetch; all pages collide in one entry
useQuery({ queryKey: ['orders'], queryFn: () => fetchOrders(page, status) });
```

```ts
// CORRECT — key mirrors the inputs; use a key factory per feature
export const orderKeys = {
  all: ['orders'] as const,
  list: (filters: { page: number; status: string }) => ['orders', 'list', filters] as const,
  detail: (id: string) => ['orders', 'detail', id] as const,
};

useQuery({ queryKey: orderKeys.list({ page, status }), queryFn: ... });
queryClient.invalidateQueries({ queryKey: orderKeys.all });   // one call nukes the feature
```

---

## `staleTime` — set it explicitly

Default `staleTime: 0` marks data stale immediately → refetch on every mount and window focus.
Right for live dashboards; flicker and wasted requests for everything else.

| Data | `staleTime` |
|---|---|
| Live/volatile (notifications, stock) | `0` (default) |
| Normal entities (users, orders) | `30_000` – `5 * 60_000` |
| Near-static (countries, plans, config) | `Infinity` + manual invalidation |

```ts
// CORRECT — app-wide default, overridden per query
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: 2 } },
});
```

`gcTime` (cache eviction for unused data, default 5 min) rarely needs changing — don't confuse
it with `staleTime`.

---

## `useMutation` — writes invalidate reads

```tsx
// WRONG — fire-and-forget fetch in a handler; list goes stale, no error feedback
const handleSave = () => { fetch('/api/orders', { method: 'POST', body }); };
```

```tsx
// CORRECT
const queryClient = useQueryClient();
const createOrder = useMutation({
  mutationFn: (input: NewOrder) => postOrder(input),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: orderKeys.all }),
  onError: (error) => toast.error(humanize(error)),
});

<button onClick={() => createOrder.mutate(draft)} disabled={createOrder.isPending}>
  {createOrder.isPending ? 'Saving…' : 'Save'}
</button>
```

---

## Optimistic updates — the three-callback contract

`onMutate` snapshots + applies the optimistic value, `onError` rolls back from the snapshot,
`onSettled` invalidates to reconcile with the server. All three or none. (Source: TanStack
Query docs — "Optimistic Updates".)

```ts
const toggleDone = useMutation({
  mutationFn: patchTodo,
  onMutate: async (todo) => {
    await queryClient.cancelQueries({ queryKey: todoKeys.all });        // don't race refetches
    const previous = queryClient.getQueryData<Todo[]>(todoKeys.all);
    queryClient.setQueryData<Todo[]>(todoKeys.all, (old = []) =>
      old.map((t) => (t.id === todo.id ? { ...t, done: !t.done } : t))
    );
    return { previous };                                                // context for rollback
  },
  onError: (_err, _todo, context) => {
    queryClient.setQueryData(todoKeys.all, context?.previous);          // rollback
  },
  onSettled: () => queryClient.invalidateQueries({ queryKey: todoKeys.all }),
});
```

---

## Dependent and conditional queries

```ts
// CORRECT — `enabled` gates the query until its input exists; never call hooks conditionally
const { data: user } = useQuery({ queryKey: ['user', email], queryFn: ... });
const { data: projects } = useQuery({
  queryKey: ['projects', user?.id],
  queryFn: () => fetchProjects(user!.id),
  enabled: !!user?.id,
});
```

---

## Error handling — never swallow

Handle errors at three levels: per-component (`isError` branch), global default (monitoring),
and boundary (`throwOnError` + ErrorBoundary for unrecoverable cases).

```tsx
// CORRECT — component-level
const { data, isPending, isError, error, refetch } = useQuery(...);
if (isPending) return <Spinner />;
if (isError) return <ErrorState message={humanize(error)} onRetry={() => refetch()} />;
```

```ts
// CORRECT — global hook for monitoring (QueryCache, not per-query)
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => reportError(error, { queryKey: query.queryKey }),
  }),
});
```

---

## Suspense mode

`useSuspenseQuery` removes the `isPending`/`isError` branches from the component — loading is
handled by the nearest `<Suspense>`, errors by the nearest ErrorBoundary. Prefer it when a
parent already owns those boundaries (e.g. Next.js `loading.tsx`/`error.tsx`).

```tsx
// CORRECT — data is non-nullable here; no loading branch in the component
const { data: orders } = useSuspenseQuery({
  queryKey: orderKeys.all,
  queryFn: fetchOrders,
});
```

---

## Pagination and infinite lists

```ts
// CORRECT — cursor-based infinite query (matches node/refs/api-design.md response shape)
const ordersQuery = useInfiniteQuery({
  queryKey: orderKeys.list({ status }),
  queryFn: ({ pageParam }) => fetchOrders({ cursor: pageParam, status }),
  initialPageParam: null as string | null,
  getNextPageParam: (lastPage) => (lastPage.hasMore ? lastPage.nextCursor : undefined),
});
```

For numbered pages, `placeholderData: keepPreviousData` shows the current page while the next
loads — no layout flash.
