# State Management — TypeScript Frontend Reference

Grounded in **TkDodo — Practical React Query** ("Server state is not client state"), the
**Zustand docs**, the **Jotai docs**, and the **React docs** (useReducer, Context).

---

## First decision: which *category* of state is this?

Most state-management pain comes from using one tool for all three categories.

| Category | What it is | Tool |
|---|---|---|
| **Server state** | Remote data: users, orders, anything fetched | **TanStack Query** (cache, refetch, sync) — see `refs/data-fetching.md` |
| **Local UI state** | One component's ephemera: open/closed, input value | `useState` / `useReducer` |
| **Shared client state** | Cross-component, client-owned: theme, cart draft, wizard step | **Zustand** or **Jotai** |
| **URL state** | Filters, sort, pagination, active tab | Search params (`useSearchParams`) |

```tsx
// WRONG — server data copied into a global store; now two sources of truth to sync
const useStore = create((set) => ({
  users: [],
  fetchUsers: async () => set({ users: await getUsers() }),
}));
```

```tsx
// CORRECT — server state lives in the Query cache, never copied out
const { data: users } = useQuery({ queryKey: ['users'], queryFn: getUsers });
```

---

## Never mirror props or query data into `useState`

Copying creates a snapshot that goes stale on the next update. Read the source directly;
derive during render. (Source: TkDodo — "Don't sync state, derive it".)

```tsx
// WRONG — `name` is frozen at mount; editing-then-refetch shows stale data
function Profile({ user }: Props) {
  const [name, setName] = useState(user.name);
  ...
}
```

```tsx
// CORRECT — read the prop; lift edit state into a keyed form when actually editing
function Profile({ user }: Props) {
  return <EditForm key={user.id} defaultValues={user} />;  // key resets the form per user
}
```

---

## `useReducer` for multi-transition local state

When one interaction updates several `useState` slices in lockstep, the state is one machine —
model it as one reducer. (Source: react.dev — "Extracting State Logic into a Reducer".)

```tsx
// WRONG — three setters that must always be called together
const [step, setStep] = useState(0);
const [answers, setAnswers] = useState<Answer[]>([]);
const [canGoBack, setCanGoBack] = useState(false);
```

```tsx
// CORRECT — transitions are explicit and exhaustively typed
type WizardState = { step: number; answers: Answer[] };
type WizardAction =
  | { type: 'answer'; payload: Answer }
  | { type: 'back' }
  | { type: 'reset' };

function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case 'answer':
      return { step: state.step + 1, answers: [...state.answers, action.payload] };
    case 'back':
      return { ...state, step: Math.max(0, state.step - 1) };
    case 'reset':
      return { step: 0, answers: [] };
  }
}

const [state, dispatch] = useReducer(wizardReducer, { step: 0, answers: [] });
```

---

## Zustand — one store per domain slice, select narrowly

(Source: Zustand docs — "TypeScript Guide", "Prevent rerenders with useShallow".)

```ts
// CORRECT — typed State & Actions; store in features/cart/store.ts
interface CartState {
  items: CartItem[];
  addItem: (item: CartItem) => void;
  removeItem: (id: string) => void;
  clear: () => void;
}

export const useCartStore = create<CartState>()((set) => ({
  items: [],
  addItem: (item) => set((s) => ({ items: [...s.items, item] })),
  removeItem: (id) => set((s) => ({ items: s.items.filter((i) => i.id !== id) })),
  clear: () => set({ items: [] }),
}));
```

```tsx
// WRONG — subscribing to the whole store re-renders on every change anywhere in it
const { items } = useCartStore();

// CORRECT — selector: re-render only when the selected slice changes
const items = useCartStore((s) => s.items);
const itemCount = useCartStore((s) => s.items.length);
```

Don't create one mega-store for the app; one store per domain (cart, ui-prefs) keeps
subscriptions narrow and modules independently testable.

---

## Jotai — atoms for fine-grained reactivity

Prefer Jotai when state is many small independent values (canvas/editor settings, per-widget
prefs) — each atom updates independently with zero selector boilerplate. Prefer Zustand when
state is one cohesive domain object with actions. (Sources: Jotai docs; Zustand docs comparison.)

```ts
// CORRECT — atoms compose; derived atoms recompute automatically
import { atom, useAtom } from 'jotai';
import { atomWithStorage } from 'jotai/utils';

export const fontSizeAtom = atomWithStorage('fontSize', 14);   // persists to localStorage
export const zoomAtom = atom(1);
export const effectiveSizeAtom = atom((get) => get(fontSizeAtom) * get(zoomAtom));
```

---

## Context — low-frequency globals only

Every context value change re-renders **all** consumers. Context is dependency injection for
rarely-changing values (theme, locale, current user), not a state manager. (Source: react.dev —
"Passing Data Deeply with Context".)

```tsx
// WRONG — form values in context: every keystroke re-renders every consumer
<FormContext.Provider value={{ values, setValues }}>
```

```tsx
// CORRECT — stable, rarely-changing value; memoized to avoid identity churn
const value = useMemo(() => ({ user, locale }), [user, locale]);
return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
```

Always pair a custom consumer hook that throws outside the provider:

```tsx
export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used inside <AppProvider>');
  return ctx;
}
```

---

## URL as state

Filters, sort order, pagination, and active tab belong in the URL: refresh-proof, shareable,
back-button-friendly, and indexable. (Source: Next.js docs — `useSearchParams`.)

```tsx
// WRONG — filter state evaporates on refresh and can't be shared
const [status, setStatus] = useState<'all' | 'open'>('all');
```

```tsx
// CORRECT — Next.js App Router
'use client';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';

const searchParams = useSearchParams();
const status = searchParams.get('status') ?? 'all';

const setStatus = (value: string) => {
  const params = new URLSearchParams(searchParams);
  params.set('status', value);
  router.replace(`${pathname}?${params.toString()}`);
};
```

---

## No module-level mutable state

A module-level `let` mutated by components bypasses React's rendering model — no re-render, no
StrictMode double-check, breaks SSR (state leaks across requests on the server).

```ts
// WRONG
let currentUser: User | null = null;
export function setCurrentUser(u: User) { currentUser = u; }
```

```ts
// CORRECT — state lives in React (context/store); server gets per-request instances
export const useSessionStore = create<SessionState>()((set) => ({ ... }));
```
