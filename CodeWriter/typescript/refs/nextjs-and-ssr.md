# Next.js & SSR — TypeScript Frontend Reference

Grounded in the **Next.js 15 App Router docs**, the **React Server Components RFC**, and
**Vercel architecture guides**. Applies to App Router only — Pages Router
(`getServerSideProps`) is legacy.

---

## Server Components by default; `'use client'` is the exception

Every component is a Server Component until marked otherwise: zero JS shipped, direct
async data access, secrets usable. Add `'use client'` only for interactivity (handlers, hooks,
browser APIs) — and push that boundary to the smallest leaf possible, because **everything a
client component imports becomes client bundle too**.

```tsx
// WRONG — 'use client' on the page shell drags the whole tree into the bundle
'use client';
export default function ProductPage() {
  return (<><ProductDetails /><Reviews /><AddToCartButton /></>);
}
```

```tsx
// CORRECT — page stays server; only the interactive leaf is client
// app/products/[slug]/page.tsx  (Server Component — no directive)
export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const product = await getProduct(slug);          // direct await — no useEffect, no API hop
  return (
    <main>
      <ProductDetails product={product} />
      <AddToCartButton productId={product.id} />   {/* the only 'use client' file */}
    </main>
  );
}
```

Server → Client props must be serializable: no functions, class instances, or Dates expected
to stay `Date`. To put server content *inside* an interactive wrapper, pass it as `children`
(composition keeps it server-rendered).

---

## Data fetching and caching in RSC

`fetch` in Server Components declares its caching inline. Next.js 15 default is **uncached**
(`no-store`) — opt *into* caching explicitly. (Source: Next.js docs — "Caching".)

```tsx
const res = await fetch(url, { cache: 'force-cache' });          // static — build-time/full cache
const res = await fetch(url, { next: { revalidate: 60 } });      // ISR — at most every 60 s
const res = await fetch(url, { next: { tags: ['products'] } });  // tag-based invalidation
const res = await fetch(url, { cache: 'no-store' });             // per-request (explicit)
```

```ts
// Mutation side: invalidate by tag or path
import { revalidateTag, revalidatePath } from 'next/cache';
revalidateTag('products');
```

Parallelize independent requests — sequential awaits are the classic RSC waterfall:

```tsx
// WRONG — second await waits for the first
const user = await getUser(id);
const orders = await getOrders(id);

// CORRECT
const [user, orders] = await Promise.all([getUser(id), getOrders(id)]);
```

For non-`fetch` data (DB clients), use `unstable_cache`/`'use cache'` or cache at the data
layer; `React.cache()` deduplicates per-request calls.

---

## Server Actions — mutations without API plumbing

`'use server'` functions are the App Router's mutation path for forms. **They are public HTTP
endpoints** — validate input with Zod and check authorization inside every action, exactly as
you would a route handler. (Source: Next.js docs — "Server Actions and Mutations / Security".)

```ts
// app/actions/create-post.ts
'use server';
import { z } from 'zod';
import { revalidatePath } from 'next/cache';

const CreatePostSchema = z.object({ title: z.string().min(3).max(120), body: z.string().min(1) });

export async function createPost(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const session = await getSession();
  if (!session) return { status: 'error', message: 'Not authenticated' };   // authz INSIDE

  const parsed = CreatePostSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { status: 'error', errors: parsed.error.flatten().fieldErrors };

  await db.post.create({ data: { ...parsed.data, authorId: session.userId } });
  revalidatePath('/posts');
  return { status: 'success' };
}
```

```tsx
// Client — useActionState wires pending/error/result
'use client';
const [state, formAction, isPending] = useActionState(createPost, { status: 'idle' });
<form action={formAction}>…<button disabled={isPending}>Publish</button></form>
```

Route handlers (`app/api/*/route.ts`) remain for webhooks, third-party callbacks, and
non-React clients — prefer Server Actions for your own forms.

---

## TanStack Query + RSC — prefetch, dehydrate, hydrate

Server prefetches into a per-request QueryClient; `HydrationBoundary` hands the cache to the
client; `useQuery` on the client starts warm and keeps the data live. (Source: TanStack Query
docs — "Advanced SSR".)

```tsx
// app/users/page.tsx (Server Component)
export default async function UsersPage() {
  const queryClient = new QueryClient();           // per-request — NEVER module-level on server
  await queryClient.prefetchQuery({ queryKey: ['users'], queryFn: fetchUsers });
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <UserList />                                  {/* 'use client'; useQuery(['users']) */}
    </HydrationBoundary>
  );
}
```

A module-level QueryClient on the server leaks data between users' requests — the singleton
pattern is browser-only.

---

## Streaming: `loading.tsx`, `error.tsx`, nested Suspense

| File | Provides |
|---|---|
| `loading.tsx` | Automatic Suspense fallback for the segment — shell paints immediately |
| `error.tsx` | Error boundary per segment (must be `'use client'`; gets `reset()`) |
| `not-found.tsx` | 404 UI for `notFound()` |

Inside a page, wrap slow subtrees in `<Suspense>` so fast content streams first — same
many-small-boundaries rule as `refs/performance-frontend.md`:

```tsx
export default function Dashboard() {
  return (
    <main>
      <Header />                                        {/* instant */}
      <Suspense fallback={<StatsSkeleton />}><Stats /></Suspense>
      <Suspense fallback={<FeedSkeleton />}><SlowFeed /></Suspense>
    </main>
  );
}
```

---

## Metadata — the API, never `<head>` tags in JSX

```tsx
// CORRECT — static
export const metadata: Metadata = { title: 'Dashboard', description: '…' };

// CORRECT — dynamic
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const product = await getProduct((await params).slug);
  return { title: product.name, openGraph: { images: [product.image] } };
}
```

`layout.tsx` sets the template (`title: { template: '%s | Acme', default: 'Acme' }`); pages set
specifics. Never render `<title>`/`<meta>` in JSX.

---

## Environment split

`NEXT_PUBLIC_*` is embedded into the client bundle at build time; everything else is
server-only. Validate both groups at startup with Zod (same discipline as
`node/refs/config-and-secrets.md`), and see `refs/security-frontend.md` for the secrets rule.
