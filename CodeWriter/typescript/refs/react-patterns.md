# React Patterns — TypeScript Frontend Reference

Grounded in the **React docs** (react.dev — "You Might Not Need an Effect", "Rules of Hooks"),
**Dan Abramov — A Complete Guide to useEffect**, and the **react-error-boundary** docs.
Enforced by `react-hooks/rules-of-hooks` and `react-hooks/exhaustive-deps` (both `error`).

---

## Component shape: function + named export, single responsibility

Functional components only — the React team has deprecated the class mental model. A component
has one reason to render; when it juggles several distinct data concerns, split it.

```tsx
// WRONG — one component fetches, filters, paginates, and renders two unrelated panels
export default function Dashboard() {
  const [users, setUsers] = useState([]);
  const [orders, setOrders] = useState([]);
  const [filter, setFilter] = useState('');
  // ...200 lines mixing user logic and order logic...
}
```

```tsx
// CORRECT — Dashboard composes; each child owns one concern
export function Dashboard() {
  return (
    <main>
      <UserPanel />
      <OrderPanel />
    </main>
  );
}
```

---

## `useEffect` discipline — only for synchronizing with external systems

The single highest-impact React rule. An Effect is for *leaving React*: subscriptions,
browser APIs, non-React widgets, analytics. It is **not** for transforming data you already
have, and **not** for reacting to user events. (Source: react.dev — "You Might Not Need an
Effect"; see `refs/data-fetching.md` for the data-fetching case.)

### Derived state: compute during render

```tsx
// WRONG — redundant state + sync Effect: extra render, stale-value window, more code
const [items, setItems] = useState<Item[]>([]);
const [visible, setVisible] = useState<Item[]>([]);
useEffect(() => {
  setVisible(items.filter((i) => i.matches(query)));
}, [items, query]);
```

```tsx
// CORRECT — derived data is a plain expression; useMemo only if measured expensive
const visible = items.filter((i) => i.matches(query));
// const visible = useMemo(() => expensiveFilter(items, query), [items, query]);
```

### Event logic: in the handler, not an Effect

```tsx
// WRONG — POST in an Effect watching a flag; fires on re-mounts, needs cleanup gymnastics
useEffect(() => {
  if (submitted) postOrder(cart);
}, [submitted]);
```

```tsx
// CORRECT — the user action runs the user's logic
const handleSubmit = async () => {
  await postOrder(cart);
  setSubmitted(true);
};
```

### A legitimate Effect — external system, with cleanup

```tsx
// CORRECT — subscribing to a browser API; cleanup mirrors setup
useEffect(() => {
  const onResize = () => setWidth(window.innerWidth);
  window.addEventListener('resize', onResize);
  return () => window.removeEventListener('resize', onResize);
}, []);
```

Never silence `exhaustive-deps` with a disable comment — a missing dependency is a stale
closure bug. Restructure (move the function inside the Effect, use the updater form of
`setState`, or extract a custom hook) instead.

---

## Memoization: measured, not ritual

`useMemo`/`useCallback`/`React.memo` have a cost (memory, dependency comparison, reader
overhead). Use them for exactly two reasons (source: react.dev — `useMemo`):

1. **Referential stability** — the value/function is a dependency of a child `React.memo` or
   another hook's dep array.
2. **Measured expense** — the computation is provably slow (React DevTools Profiler first).

```tsx
// WRONG — ritual memoization of a cheap value passed to a non-memoized child
const label = useMemo(() => `${first} ${last}`, [first, last]);
const handleClick = useCallback(() => setOpen(true), []);
return <PlainChild label={label} onClick={handleClick} />;
```

```tsx
// CORRECT — stability matters here: Row is memoized and re-renders 5,000 times otherwise
const handleSelect = useCallback((id: string) => setSelected(id), []);
return rows.map((r) => <MemoRow key={r.id} row={r} onSelect={handleSelect} />);
```

React 19's compiler will automate much of this — one more reason not to hand-strew memo calls.

---

## Composition over prop drilling

When a prop tunnels through 3+ levels untouched, restructure instead of relaying. Options in
order of preference: **children composition** → **compound components** → **context**.

```tsx
// WRONG — `user` drills through Layout and Sidebar just to reach Avatar
<Layout user={user}><Sidebar user={user} /></Layout>
```

```tsx
// CORRECT — composition: the owner renders Avatar and passes it down as JSX
<Layout sidebar={<Sidebar footer={<Avatar user={user} />} />} />

// CORRECT — compound components share implicit state via context
<Tabs defaultValue="a">
  <Tabs.List>
    <Tabs.Trigger value="a">First</Tabs.Trigger>
  </Tabs.List>
  <Tabs.Content value="a">...</Tabs.Content>
</Tabs>
```

---

## Keys: stable identity, not array index

Index keys make React reuse the wrong DOM/state when the list reorders, inserts, or deletes —
the classic "my checkbox jumped to another row" bug. (Source: react.dev — "Rendering Lists".)

```tsx
// WRONG — index key on a mutable list
{todos.map((todo, i) => <TodoRow key={i} todo={todo} />)}
```

```tsx
// CORRECT — identity from the data
{todos.map((todo) => <TodoRow key={todo.id} todo={todo} />)}
```

Index keys are acceptable only for lists that never reorder, filter, or change length.

---

## Conditional rendering

| Situation | Pattern |
|---|---|
| Render-or-nothing | `{isOpen && <Modal />}` |
| Either/or | `{isAdmin ? <AdminView /> : <UserView />}` |
| Multiple guards / complex | Early returns at the top of the component |

```tsx
// WRONG — `count && <Badge />` renders the literal 0 when count is 0
{count && <Badge count={count} />}

// CORRECT — force the boolean
{count > 0 && <Badge count={count} />}
```

```tsx
// CORRECT — early returns keep the happy path unindented
export function UserProfile({ userId }: Props) {
  const { data: user, isPending, isError } = useUser(userId);
  if (isPending) return <Spinner />;
  if (isError) return <ErrorState />;
  return <ProfileCard user={user} />;
}
```

---

## Error boundaries around async subtrees

A render error anywhere unmounts the whole tree unless a boundary catches it. Use
**react-error-boundary** (functional API) around every async/risky subtree; always provide a
fallback with a retry path.

```tsx
// CORRECT
import { ErrorBoundary } from 'react-error-boundary';

<ErrorBoundary
  FallbackComponent={({ error, resetErrorBoundary }) => (
    <ErrorState message={error.message} onRetry={resetErrorBoundary} />
  )}
  onError={(error) => reportError(error)}
>
  <Suspense fallback={<Spinner />}>
    <OrderHistory />
  </Suspense>
</ErrorBoundary>
```

In Next.js App Router, `error.tsx` per route segment provides this automatically — see
`refs/nextjs-and-ssr.md`.

---

## Avoid HOCs and render-prop wrappers in new code

Hooks replaced both patterns for logic reuse. Write a custom hook unless a library forces a
wrapper.

```tsx
// WRONG (legacy) — withAuth(withTheme(withRouter(Component))) wrapper hell
export default withAuth(ProfilePage);
```

```tsx
// CORRECT — hooks compose flat
export function ProfilePage() {
  const user = useCurrentUser();
  const theme = useTheme();
  ...
}
```
