# API Contracts — TypeScript Frontend Reference

Grounded in the **Zod docs**, the **tRPC docs**, and **OWASP API Security Top 10**. Pairs with
`node/refs/security-web.md` (server-side validation) — the same Zod discipline on both sides of
the stack.

---

## Every network response is `unknown` until Zod says otherwise

An `as MyType` cast on a fetch response is a contract written in invisible ink — the server can
change, and the client lies until something crashes far from the cause. Validate at the
boundary; trust everywhere inside it.

```ts
// WRONG — the cast guarantees nothing; failure surfaces as "cannot read property of undefined"
// three components deep
const res = await fetch('/api/users');
const users = (await res.json()) as User[];
```

```ts
// CORRECT — schema is the single source of truth; the TS type derives from it
import { z } from 'zod';

export const UserSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  email: z.string().email(),
  role: z.enum(['admin', 'member']),
});
export type User = z.infer<typeof UserSchema>;       // never hand-write the type twice

const body: unknown = await res.json();
const result = z.array(UserSchema).safeParse(body);
if (!result.success) throw new ApiError('INVALID_RESPONSE', result.error);
return result.data;                                  // fully typed User[]
```

---

## `safeParse` vs `parse`

| Use | Where |
|---|---|
| `safeParse` — returns `{ success, data | error }` | Anywhere the failure is *handled*: fetch wrappers, hooks, form input |
| `parse` — throws `ZodError` | Trusted internal boundaries where a failure is a programmer error (env at startup, test fixtures) |

```ts
// WRONG — parse() in a component: a malformed response becomes an uncaught render crash
const user = UserSchema.parse(await res.json());
```

---

## Centralized fetch wrapper — validate once, type everywhere

One `apiFetch` owns: base URL, auth header, response validation, and typed errors. Call sites
never touch raw `fetch` or raw JSON.

```ts
// lib/api-client.ts
export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiFetch<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${API.BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });

  if (!res.ok) {
    const problem = ProblemSchema.safeParse(await res.json().catch(() => null));
    throw new ApiError(
      problem.success ? problem.data.type : 'HTTP_ERROR',
      res.status,
      problem.success ? problem.data.detail : res.statusText
    );
  }

  const body: unknown = await res.json();
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError('INVALID_RESPONSE', res.status, parsed.error.message);
  }
  return parsed.data;
}
```

```ts
// CORRECT — call sites are one line and fully typed
export const fetchUsers = (signal?: AbortSignal) =>
  apiFetch('/users', z.array(UserSchema), { signal });
```

---

## Error shapes — one contract, validated like data

The backend (per `node/refs/error-handling-web.md`) returns RFC 9457 Problem Details. The
frontend validates error bodies with a schema too — error paths are the *least* tested and the
most likely to have shape drift.

```ts
export const ProblemSchema = z.object({
  type: z.string(),
  title: z.string(),
  status: z.number(),
  detail: z.string(),
  instance: z.string().optional(),
});
```

```tsx
// CORRECT — a single humanize() maps typed errors to user-facing copy
export function humanize(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Your session expired. Please sign in again.';
    if (error.status === 429) return 'Too many requests — try again in a minute.';
    return error.message;
  }
  return 'Something went wrong. Please try again.';
}
```

---

## Schema placement and type sharing

- Co-locate schemas with the API call (`features/users/api.ts`) or in a `schemas/` directory —
  one schema per endpoint response shape.
- In a full-stack TS monorepo, define schemas **once** in a shared package; server validates
  input with them, client validates responses with them. Duplicated type definitions on the two
  sides *will* drift.

```text
packages/
├── shared/src/schemas/user.ts    ← UserSchema lives here, once
├── api/…                         ← imports UserSchema for input validation
└── web/…                         ← imports UserSchema for response validation
```

---

## tRPC — when you own both ends

For full-stack TypeScript monorepos, tRPC gives end-to-end type safety with **no code
generation**: procedures declare Zod input/output, the client gets typed calls and TanStack
Query integration for free. (Source: tRPC docs.)

```ts
// server — input is validated at runtime AND typed at compile time
export const userRouter = router({
  byId: publicProcedure
    .input(z.object({ id: z.string().uuid() }))
    .query(({ input }) => userService.byId(input.id)),
});
```

```tsx
// client — typo in the key or wrong input type = compile error
const { data: user } = trpc.user.byId.useQuery({ id });
```

| Choose | When |
|---|---|
| **tRPC** | Internal app, TS on both sides, one repo |
| **REST + Zod wrapper** | Public API, polyglot consumers, OpenAPI needed |

Never trust client-side validation alone — the server re-validates every input regardless
(OWASP API2/API3). Client-side Zod is for UX and type safety, not security.
