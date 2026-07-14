# TypeScript Strict Mode — TypeScript Frontend Reference

Grounded in the **TypeScript Handbook**, **`@tsconfig/strictest`**, and the
**React TypeScript Cheatsheet** (react-typescript-cheatsheet.netlify.app). Enforced by
`tooling/tsconfig.base.json` and `@typescript-eslint` rules `no-explicit-any`,
`consistent-type-imports`.

---

## Base config — frontend deltas over the `node/` baseline

The frontend tsconfig shares the strict baseline with `node/tooling/tsconfig.base.json`
(`strict`, `verbatimModuleSyntax`, `noUncheckedIndexedAccess`, `isolatedModules`) and adds:

| Option | Value | Why |
|---|---|---|
| `jsx` | `"react-jsx"` | Automatic JSX runtime — no `import React` needed (TS 4.1+, React 17+) |
| `lib` | `["ES2023", "DOM", "DOM.Iterable"]` | Browser globals (`window`, `document`, `NodeList` iteration) |
| `moduleResolution` | `"bundler"` | Vite/Next.js resolve imports; allows extensionless imports |
| `noEmit` | `true` | `tsc` is the type-checker only; Vite/Next.js own emit |

Never weaken `strict`. If a third-party type forces a compromise, isolate it in one file with a
`// eslint-disable` + reason comment — don't lower the project-wide bar.

---

## `unknown` at every boundary

Anything that crosses the network or a `catch` clause is `unknown` until validated. Casting with
`as` is a promise the runtime never checks. (Source: TS Handbook "unknown"; see
`refs/api-contracts.md` for the Zod side.)

```ts
// WRONG — `as` cast: if the API changes shape, this lies until production crashes
const res = await fetch('/api/user');
const user = (await res.json()) as User;

try { ... } catch (err) {
  console.error(err.message);          // err is any (or unknown error) — may not have .message
}
```

```ts
// CORRECT — unknown in, validated or narrowed out
const res = await fetch('/api/user');
const body: unknown = await res.json();
const user = UserSchema.parse(body);   // Zod validates; throws with a precise message

try { ... } catch (err: unknown) {
  const message = err instanceof Error ? err.message : String(err);
  reportError(message);
}
```

---

## Component props: explicit interface, never `any`

```tsx
// WRONG — any props compile against everything and document nothing
function PriceTag(props: any) {
  return <span>{props.amount.toFixed(2)}</span>;   // runtime crash if amount is a string
}
```

```tsx
// CORRECT — explicit Props interface; destructure in the signature
interface Props {
  amount: number;
  currency?: string;            // optional with a default, not `currency: string | undefined`
}

export function PriceTag({ amount, currency = 'EUR' }: Props) {
  return <span>{formatCurrency(amount, currency)}</span>;
}
```

Avoid `React.FC` — it is no longer recommended by the React TypeScript Cheatsheet: it implied
`children` pre-React-18, breaks generic components, and adds nothing over typing props directly.

---

## `children` and element types

| Need | Type |
|---|---|
| "Anything renderable" (default) | `React.ReactNode` |
| Exactly one element (e.g. to clone it) | `React.ReactElement` |
| A component you will render yourself | `React.ComponentType<P>` |
| Polymorphic `as` prop | `React.ElementType` |

```tsx
// CORRECT — ReactNode accepts strings, numbers, elements, fragments, null
interface Props {
  children: React.ReactNode;
}
export function Panel({ children }: Props) {
  return <section className="panel">{children}</section>;
}
```

---

## Event types — name the element, not `any`

```tsx
// WRONG
const handleChange = (e: any) => setQuery(e.target.value);
```

```tsx
// CORRECT — the generic names the element, so .target is fully typed
const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => setQuery(e.target.value);
const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => { e.preventDefault(); ... };
const handleKey = (e: React.KeyboardEvent<HTMLButtonElement>) => { if (e.key === 'Enter') ... };
```

When the handler is inline in JSX, TypeScript infers the event type — only annotate when the
handler is declared separately.

---

## `useRef` — explicit generic, three shapes

(Source: React TypeScript Cheatsheet — "useRef".)

```tsx
// WRONG — untyped null ref; .current is null forever to the type system
const inputRef = useRef(null);
inputRef.current.focus();                       // error AND no autocomplete

// CORRECT — DOM ref: generic + null initial; read-only .current managed by React
const inputRef = useRef<HTMLInputElement>(null);
inputRef.current?.focus();

// CORRECT — mutable value ref (instance variable that doesn't trigger renders)
const timerId = useRef<ReturnType<typeof setTimeout> | null>(null);
timerId.current = setTimeout(tick, 1000);
```

---

## `useState` with explicit generics when inference fails

```tsx
// WRONG — inferred as null; setUser(user) is a type error later
const [user, setUser] = useState(null);

// CORRECT
const [user, setUser] = useState<User | null>(null);
const [items, setItems] = useState<Item[]>([]);     // [] alone infers never[]
```

---

## Generic components

```tsx
// WRONG — any[] erases the relationship between items and renderItem
interface Props { items: any[]; renderItem: (item: any) => React.ReactNode }
```

```tsx
// CORRECT — the generic flows from items to renderItem to keyOf
interface Props<T> {
  items: T[];
  keyOf: (item: T) => string;
  renderItem: (item: T) => React.ReactNode;
}

export function List<T>({ items, keyOf, renderItem }: Props<T>) {
  return <ul>{items.map((item) => <li key={keyOf(item)}>{renderItem(item)}</li>)}</ul>;
}
```

---

## `noUncheckedIndexedAccess` in UI code

Array indexing returns `T | undefined` — exactly right for list UIs fed by remote data.

```tsx
// WRONG (and a compile error under this flag) — users[0] may be undefined
const first = users[0];
return <h1>{first.name}</h1>;
```

```tsx
// CORRECT — handle the empty case in the UI, where it belongs
const first = users[0];
if (!first) return <EmptyState message="No users yet" />;
return <h1>{first.name}</h1>;
```

---

## Cross-project `extends` and shared tooling configs

TypeScript resolves every `extends` chain **relative to the file being extended**, not the
project root. When a `tsconfig.json` at `/projects/my-app/` extends a file at
`/shared/tooling/tsconfig.base.json`, and that base file in turn extends `@tsconfig/strictest`,
TypeScript looks for `@tsconfig/strictest` in `/shared/tooling/node_modules/` — not in
`/projects/my-app/node_modules/`. If the shared tooling directory has no `node_modules`, the
compile fails with `Cannot find base config file` or a confusing package-not-found error.

**When the base config is outside the project root, inline the flags instead of extending.**

```jsonc
// ❌ WRONG — fails if /shared/tooling/node_modules/@tsconfig/ does not exist
{
  "extends": "/shared/tooling/tsconfig.base.json"
}
```

```jsonc
// ✅ CORRECT — flags inlined; add a comment pointing to the canonical source
// Compiler flags sourced from Dev_Skills/CodeWriter/typescript/tooling/tsconfig.base.json.
// Cannot extend across filesystem: TypeScript resolves transitive extends relative to the
// extended file's directory, so @tsconfig/strictest must be installed there — not here.
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
    // ... other flags copied from the base
  }
}
```

`extends` works correctly when the base is **inside the project** (e.g. `./tsconfig.base.json`
or a workspace package's `tsconfig.json`) because `node_modules` resolution then starts from the
project root where dependencies are installed.

---

## `Awaited<ReturnType<typeof fn>>` for async SDK methods

When a third-party SDK doesn't re-export the return type of a function, use the built-in utility
types to derive it instead of casting with `as`.

```ts
// WRONG — as cast: no compile-time safety if the SDK changes the shape
let event: SomeEventType;
try {
  event = await sdk.webhooks.unmarshal(body, secret, sig) as SomeEventType;
} catch { ... }
```

```ts
// CORRECT — derive the type from the function signature
let event: Awaited<ReturnType<typeof sdk.webhooks.unmarshal>>;
try {
  event = await sdk.webhooks.unmarshal(body, secret, sig);
} catch { ... }
```

`Awaited<T>` unwraps `Promise<T>` — essential when `unmarshal` returns `Promise<EventEntity>`
but the non-Promise type is internal and not exported by the SDK.

Also applies to `ReturnType<typeof someClass.someMethod>` for sync methods. Use this pattern
any time TypeScript cannot infer the type from assignment alone (e.g. a `let` that is assigned
inside a `try` block).

---

## SDK enum and constant casing

Always read the SDK's TypeScript declarations rather than assuming casing from documentation or
examples written for an older version. Many SDKs shift from `SCREAMING_SNAKE` or `PascalCase`
enum members to `camelCase` or lowercase literals across major versions.

```ts
// WRONG — casing from docs example that was written for an older SDK version
import { Environment } from '@paddle/paddle-node-sdk';
new Paddle(key, { environment: Environment.Production });  // error: no such member
```

```ts
// CORRECT — verified from the SDK's types in node_modules
import { Environment } from '@paddle/paddle-node-sdk';
new Paddle(key, { environment: Environment.production });  // ✅ actual member name
```

Diagnostic: `Property 'X' does not exist on type '...' Did you mean 'y'?` — TypeScript gives
the correct name in the error. Read the suggestion before googling.

---

## `import type` and `satisfies`

`verbatimModuleSyntax` requires `import type` for type-only imports — bundlers can then drop
them without analysis. Use `satisfies` to validate a value against a type while keeping the
narrower inferred type (TS 4.9+).

```ts
// CORRECT
import type { Metadata } from 'next';
import { z } from 'zod';

export const metadata = {
  title: 'Dashboard',
  description: 'Team dashboard',
} satisfies Metadata;          // checked against Metadata, but .title stays the literal type
```

```ts
// WRONG — `as` would silence a typo; satisfies catches it
export const metadata = { titel: 'Dashboard' } as Metadata;        // compiles!
export const metadata = { titel: 'Dashboard' } satisfies Metadata; // error: 'titel' unknown
```
