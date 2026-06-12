# Naming & File Layout — TypeScript Frontend Reference

Grounded in the **Airbnb React/JSX Style Guide**, the **React docs** (react.dev — Rules of
Hooks), and the **Next.js App Router file conventions**. ESLint rules `react-hooks/rules-of-hooks`,
`react/jsx-pascal-case`, and `@typescript-eslint/naming-convention` enforce the conventions below.

---

## Naming conventions

| Target | Convention | Example |
|---|---|---|
| Components | `PascalCase` — file and function name match | `UserCard.tsx` → `export function UserCard()` |
| Custom hooks | `use` prefix + `camelCase`; file `use-*.ts` or `useThing.ts` | `useDebounce.ts` → `export function useDebounce()` |
| Utilities / helpers | `camelCase.ts`; pure functions, no JSX | `formatCurrency.ts`, `parseQueryParams.ts` |
| Types / interfaces | `PascalCase`; no `I` prefix | `UserProfile`, `Props`, `ApiError` |
| Constants | `UPPER_SNAKE_CASE`; grouped via `as const` objects | `MAX_UPLOAD_MB`, `ROUTES` |
| Directories | `kebab-case/` | `user-settings/`, `order-history/` |
| Next.js route segments | App Router conventions | `(marketing)/`, `[slug]/`, `@modal/` |
| Boolean props | `is*`, `has*`, or bare adjective | `isLoading`, `hasError`, `disabled` |
| Event handler functions | `handle*` | `handleClick`, `handleSubmit` |
| Event handler props | `on*` | `onClick`, `onRetry`, `onValueChange` |

```tsx
// WRONG — case soup, type prefixes, handler/prop names swapped
interface IUserCardProps { Loading: boolean; handleRetry: () => void }
function userCard({ Loading, handleRetry }: IUserCardProps) {
  const OnClick = () => { ... };
  return <div onClick={OnClick}>...</div>;
}
```

```tsx
// CORRECT — PascalCase component, is* boolean, on* prop, handle* local function
interface Props {
  isLoading: boolean;
  onRetry: () => void;
}

export function UserCard({ isLoading, onRetry }: Props) {
  const handleClick = () => { onRetry(); };
  return <button onClick={handleClick}>Retry</button>;
}
```

---

## Components: one per file, name matches filename

One exported component per file is the Airbnb default; co-located *private* subcomponents that
are not exported are fine. The export name must match the filename so search, auto-import, and
React DevTools all agree.

```tsx
// WRONG — three exported components in card.tsx; none matches the filename
export function UserCard() { ... }
export function UserCardHeader() { ... }
export function AdminBadge() { ... }
```

```tsx
// CORRECT — UserCard.tsx exports UserCard; private helper stays unexported
function CardHeader({ title }: { title: string }) {     // not exported — implementation detail
  return <h2>{title}</h2>;
}

export function UserCard({ user }: Props) {
  return (
    <article>
      <CardHeader title={user.name} />
      ...
    </article>
  );
}
```

---

## Custom hooks: the `use` prefix is load-bearing

The `use` prefix is not a style choice — it is how the React linter knows to enforce the Rules
of Hooks (call order, top-level only). A hook without the prefix silently escapes
`react-hooks/rules-of-hooks` checking; a non-hook *with* the prefix gets false errors.
(Source: react.dev — "Rules of Hooks".)

```ts
// WRONG — calls useState but isn't named use*; linter cannot check call sites
export function debouncedValue<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  ...
}
```

```ts
// CORRECT — useDebounce.ts
export function useDebounce<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}
```

---

## `interface` for props, `type` for unions and aliases

Both work; the convention (React TypeScript Cheatsheet) is `interface Props` for component props
(extendable, better error messages) and `type` for unions, mapped types, and aliases.

```tsx
// CORRECT
interface Props {
  variant: ButtonVariant;
  children: React.ReactNode;
}

type ButtonVariant = 'primary' | 'secondary' | 'ghost';
type AsyncState<T> = { status: 'idle' } | { status: 'loading' } | { status: 'done'; data: T };
```

---

## Constants: `as const` objects over loose exports

```ts
// WRONG — scattered, mutable, no namespace
export let maxRetries = 3;
export const apiUrl = '/api';
export const api_timeout = 5000;
```

```ts
// CORRECT — constants.ts; as const gives literal types and immutability
export const API = {
  BASE_URL: '/api',
  TIMEOUT_MS: 5_000,
  MAX_RETRIES: 3,
} as const;

export const ROUTES = {
  HOME: '/',
  SETTINGS: '/settings',
  USER: (id: string) => `/users/${id}`,
} as const;
```

---

## Feature co-location

Group by feature, not by kind. A feature directory holds the component, its hook, types, tests,
and styles — deleting the directory deletes the feature. (Source: Next.js docs "Project
Organization"; community consensus per Josh Comeau / bulletproof-react.)

```text
// WRONG — grouped by kind; one feature is smeared across five directories
src/
├── components/UserSettings.tsx
├── hooks/useUserSettings.ts
├── types/userSettings.ts
├── styles/UserSettings.module.css
└── __tests__/UserSettings.test.tsx
```

```text
// CORRECT — grouped by feature; everything travels together
src/
├── features/
│   └── user-settings/
│       ├── UserSettings.tsx
│       ├── UserSettings.test.tsx
│       ├── UserSettings.module.css
│       ├── useUserSettings.ts
│       ├── types.ts
│       └── index.ts                ← public API of the feature
├── components/                     ← only truly shared primitives (Button, Modal)
└── lib/                            ← shared non-React utilities
```

---

## Barrel files: deliberate public API, not a dumping ground

An `index.ts` barrel defines what a feature exposes. Re-exporting *everything* defeats
tree-shaking, creates circular-import hazards, and (in Next.js) can pull client-only code into
Server Components.

```ts
// WRONG — wildcard re-export; internals leak, bundlers struggle to shake
export * from './UserSettings';
export * from './useUserSettings';
export * from './types';
export * from './helpers';          // internal!
```

```ts
// CORRECT — explicit, minimal public surface
export { UserSettings } from './UserSettings';
export type { UserSettingsProps } from './types';
// useUserSettings and helpers stay internal to the feature
```

---

## Next.js App Router file conventions

Special filenames are framework contracts — never repurpose them. (Source: Next.js docs
"File Conventions".)

| File | Role |
|---|---|
| `page.tsx` | Route UI — makes the segment publicly routable |
| `layout.tsx` | Shared shell; preserves state across navigation |
| `loading.tsx` | Suspense fallback for the segment |
| `error.tsx` | Error boundary for the segment (must be `'use client'`) |
| `route.ts` | API route handler — never coexists with `page.tsx` |
| `(group)/` | Route group — organizes without affecting the URL |
| `[slug]/` | Dynamic segment |
| `_private/` | Underscore prefix opts a folder out of routing |

Components used by a route but not routable themselves go in `_components/` inside the segment
or in `src/features/` — never as loose siblings of `page.tsx` with reserved-looking names.
