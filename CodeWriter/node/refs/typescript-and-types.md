# TypeScript & Types — Node.js Reference

Grounded in the **TypeScript Handbook**, **`@tsconfig/node22` baseline**, **`verbatimModuleSyntax`
RFC**, and the **typescript-eslint strict ruleset**. The target is TypeScript 5.5+ on Node.js 22 LTS.
`tsc --noEmit` in CI and `tsx` in development are the standard execution model.

---

## `strict` is non-negotiable

`"strict": true` is a single switch that enables the subset of checks responsible for most
real TypeScript bugs. Disabling any sub-flag must be justified in a comment next to the config.

| Flag enabled by `strict` | What it catches |
|---|---|
| `strictNullChecks` | `null`/`undefined` not assignable to typed values; forces explicit handling |
| `noImplicitAny` | Untyped parameters and variables; the most common source of type holes |
| `strictFunctionTypes` | Covariant/contravariant function argument checks |
| `strictPropertyInitialization` | Class properties must be initialized in constructor or marked `!` |
| `strictBindCallApply` | Typed `bind`/`call`/`apply` arguments |

```ts
// WRONG — strict disabled; TypeScript becomes documentation, not a safety net
{
  "compilerOptions": {
    "strict": false,
    "noImplicitAny": false
  }
}
```

```ts
// CORRECT — strict always on
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true   // bonus: arr[0] returns T | undefined
  }
}
```

---

## `verbatimModuleSyntax` — required for native type stripping

Node.js 22+ can strip type annotations without transpilation (`--experimental-strip-types`).
For this to work, type-only imports must use `import type` — otherwise the runtime sees an
import that resolves to nothing and throws. `verbatimModuleSyntax` makes the TypeScript
compiler enforce this.

```ts
// WRONG — imports a type at runtime; fails under --experimental-strip-types
import { User } from './user.js';       // User is a type — no runtime value emitted
```

```ts
// CORRECT — import type is erased before runtime; no module resolution needed
import type { User } from './user.js';
import { getUserById } from './user-service.js';  // value import — kept
```

ESLint: `@typescript-eslint/consistent-type-imports` enforces this automatically.

---

## `unknown` at boundaries, never `any`

`any` disables type checking entirely — every bug it hides becomes a runtime crash. `unknown`
is the safe alternative: it accepts any value but forces you to narrow it before use.

```ts
// WRONG — any spreads type holes through the codebase
async function parseJson(raw: string): any {
  return JSON.parse(raw);                   // caller gets any; all bets are off
}

try {
  await doWork();
} catch (err: any) {
  logger.error(err.message);               // crashes if err is not an Error
}
```

```ts
// CORRECT — unknown forces explicit narrowing
function parseJson(raw: string): unknown {
  return JSON.parse(raw);
}

try {
  await doWork();
} catch (err: unknown) {
  if (err instanceof Error) {
    logger.error({ err }, err.message);
  } else {
    logger.error({ err }, 'unknown error type');
  }
}
```

Use `any` only as a deliberate escape hatch with a comment explaining why — e.g. a third-party
library that ships no types and has no `@types/` package.

---

## Explicit return types on public functions

Type inference is great for locals; public functions need explicit return types so callers have a
contract and refactors that widen the return type fail at the function, not at each call site.

```ts
// WRONG — inferred return; callers depend on the implementation detail
async function fetchUser(id: string) {
  const row = await db.query('SELECT * FROM users WHERE id = ?', [id]);
  return row;                    // inferred as whatever db.query returns
}
```

```ts
// CORRECT — explicit return type is the contract
async function fetchUser(id: string): Promise<User | null> {
  const row = await db.query<UserRow>('SELECT * FROM users WHERE id = ?', [id]);
  return row ?? null;
}
```

Exception: internal helpers and single-expression lambdas where the type is obvious at the call
site — let inference work there.

---

## Union / intersection types

Use `|` union syntax (TypeScript 4.0+) and `&` intersection. Never reach for `Object` or `{}` as
a type — use `Record<string, unknown>` for open objects and specific types for everything else.

```ts
// WRONG
type Result = Object;                  // meaningless; accepts primitives too
type MaybeUser = null | undefined | User;  // verbose; use T | null | undefined
```

```ts
// CORRECT
type MaybeUser = User | null;
type ApiResult<T> = { data: T; status: number } | { error: string; status: number };
type AdminUser = User & { role: 'admin'; permissions: string[] };
```

---

## Utility types — use stdlib before re-declaring

TypeScript ships utility types for the most common transformations. Using them reduces boilerplate
and documents intent.

| Utility | Use when |
|---|---|
| `Partial<T>` | All fields become optional (update payloads) |
| `Required<T>` | All fields become required (final validated state) |
| `Readonly<T>` | Prevent mutation after construction |
| `Pick<T, K>` | Select a subset of fields |
| `Omit<T, K>` | Exclude specific fields (e.g. strip `password` from `User`) |
| `ReturnType<typeof fn>` | Infer the return type of a function you don't control |
| `Parameters<typeof fn>` | Infer the parameter tuple of a function |
| `NonNullable<T>` | Remove `null | undefined` from a union |

```ts
// WRONG — manual re-declaration drifts from the source type
type UserUpdate = {
  name?: string;
  email?: string;
};
```

```ts
// CORRECT — derives from User; stays in sync automatically
type UserUpdate = Partial<Pick<User, 'name' | 'email'>>;
type PublicUser = Omit<User, 'password' | 'hashedToken'>;
```

---

## Generics — named descriptively at scale

`T` is fine for a single unconstrained type parameter. Use descriptive names when there are
multiple or when the constraint matters.

```ts
// WRONG — T, U, V are opaque when there are three of them
function transform<T, U, V>(fn: (a: T) => U, fallback: V): (a: T) => U | V { ... }
```

```ts
// CORRECT — descriptive names document intent
function transform<TInput, TOutput, TFallback>(
  fn: (input: TInput) => TOutput,
  fallback: TFallback,
): (input: TInput) => TOutput | TFallback { ... }

// Constraint: only objects with an id field can be cached
function cacheById<TEntity extends { id: string }>(entity: TEntity): void { ... }
```

---

## `satisfies` operator (TypeScript 4.9+)

`satisfies` verifies a value matches a type while preserving the narrower inferred type —
`as` casts lose narrowing, `satisfies` keeps it.

```ts
// WRONG — 'as' loses the literal types
const config = {
  host: 'localhost',
  port: 5432,
} as DatabaseConfig;
// config.port is now `number`, not `5432`
```

```ts
// CORRECT — satisfies validates the shape; literal types are preserved
const config = {
  host: 'localhost',
  port: 5432,
} satisfies DatabaseConfig;
// config.port is still `5432`; config.host is still `'localhost'`
```

---

## Enums — avoid numeric; prefer `const` or `as const` unions

Numeric `enum` leaks implementation details and allows invalid values to be passed as numbers.
String-valued `const enum` compiles away. For simple flags, an `as const` object + union type is
the most tree-shakeable pattern.

```ts
// WRONG — numeric enum; `Status.Active === 0` is a runtime fact; 99 is also valid Status
enum Status {
  Active,     // 0
  Inactive,   // 1
}
```

```ts
// CORRECT (option A) — const enum compiles away completely
const enum Direction {
  Up = 'UP',
  Down = 'DOWN',
}

// CORRECT (option B) — as const object + union; works with JSON, no TS magic
const HttpMethod = { Get: 'GET', Post: 'POST', Delete: 'DELETE' } as const;
type HttpMethod = typeof HttpMethod[keyof typeof HttpMethod];  // 'GET' | 'POST' | 'DELETE'
```

Use `StrEnum` pattern (string values) when the enum value must round-trip through JSON or be
stored in a database — numeric values are opaque to external systems.

---

## `interface` vs `type`

| Use | When |
|---|---|
| `interface` | Object shapes that describe external contracts (API response, class shape); may be augmented with declaration merging |
| `type` | Unions, intersections, aliases, mapped types, conditional types, or anything that can't be expressed as an `interface` |

```ts
// CORRECT — interface for external shape contract
interface UserResponse {
  id: string;
  email: string;
  createdAt: string;
}

// CORRECT — type for union / transformation
type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };
type ReadonlyUser = Readonly<UserResponse>;
```

---

## TypeScript version matrix

Match syntax to the project's `engines.node` field. `ruff`'s analogue here is `tsc --target`.

| Feature | TS version | Node requirement |
|---|---|---|
| `satisfies` operator | 4.9+ | any |
| `const` type parameter (`<const T>`) | 5.0+ | any |
| `using` / `Symbol.dispose` (explicit resource management) | 5.2+ | Node 22+ |
| Inferred type predicates | 5.5+ | any |
| Native type stripping (`--experimental-strip-types`) | runtime, not TS | Node 22.6+ |
| Type stripping without flag | runtime | Node 24+ |

Default to **TypeScript 5.5+** for new projects on Node.js 22. The `@tsconfig/node22` base
config sets the correct target; override only when targeting an older runtime.
