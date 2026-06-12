# Frontend Performance — TypeScript Frontend Reference

Grounded in the **React docs** (lazy, Suspense, useTransition, Profiler), **web.dev Core Web
Vitals**, and the **Next.js/Vite optimization docs**. Rule zero: **measure first** — bundle
analyzer and React Profiler before any optimization; never optimize blindly.

---

## Core Web Vitals — the targets

| Metric | Good | Frontend levers |
|---|---|---|
| **LCP** (Largest Contentful Paint) | < 2.5 s | Server render, image optimization, font preload, no client-fetch waterfalls for above-fold content |
| **CLS** (Cumulative Layout Shift) | < 0.1 | Reserve space: width/height on images, skeletons sized like content, `next/font` |
| **INP** (Interaction to Next Paint) | < 200 ms | Small handlers, `useTransition`/`useDeferredValue`, less main-thread JS |

Measure on real devices: Lighthouse for lab, CrUX/web-vitals library for field data.

---

## Code splitting — route-level by default

Every route and heavy feature (chart library, editor, map) loads on demand. Next.js splits per
route automatically; in Vite SPAs use `React.lazy` on route components.

```tsx
// WRONG — admin panel + charting lib in the public landing-page bundle
import { AdminPanel } from './AdminPanel';
```

```tsx
// CORRECT — loaded when (and if) visited
import { lazy, Suspense } from 'react';
const AdminPanel = lazy(() => import('./AdminPanel'));

<Suspense fallback={<PanelSkeleton />}>
  {isAdmin && <AdminPanel />}
</Suspense>
```

```tsx
// CORRECT — Next.js: client-only heavy widget
const RichEditor = dynamic(() => import('@/features/editor/RichEditor'), {
  ssr: false,
  loading: () => <EditorSkeleton />,
});
```

---

## Suspense boundaries — many small, not one global

One root spinner blocks everything behind the slowest query. Co-locate boundaries with each
async region so fast content paints immediately. (Source: react.dev — Suspense.)

```tsx
// WRONG — whole page held hostage by the slowest panel
<Suspense fallback={<FullPageSpinner />}>
  <Header /><Stats /><ActivityFeed /><SlowRecommendations />
</Suspense>
```

```tsx
// CORRECT — independent regions stream independently
<Header />
<Suspense fallback={<StatsSkeleton />}><Stats /></Suspense>
<Suspense fallback={<FeedSkeleton />}><ActivityFeed /></Suspense>
<Suspense fallback={null}><SlowRecommendations /></Suspense>
```

Skeletons must occupy the same dimensions as the loaded content — that's the CLS defense.

---

## Keeping input responsive: `useTransition` / `useDeferredValue`

Concurrent React tools for "typing feels laggy because each keystroke re-renders something
big". They de-prioritize the heavy render so the input stays at 60fps — complementary to
debouncing (which reduces *work*), not a replacement.

```tsx
// WRONG — every keystroke synchronously re-renders 5,000 filtered rows
const [query, setQuery] = useState('');
const results = filterRows(rows, query);
```

```tsx
// CORRECT — useDeferredValue: input updates now, list re-renders when there's slack
const [query, setQuery] = useState('');
const deferredQuery = useDeferredValue(query);
const results = useMemo(() => filterRows(rows, deferredQuery), [rows, deferredQuery]);
const isStale = query !== deferredQuery;

<input value={query} onChange={(e) => setQuery(e.target.value)} />
<div style={{ opacity: isStale ? 0.6 : 1 }}><Results rows={results} /></div>
```

```tsx
// CORRECT — useTransition for non-urgent state changes (tab switches, filters)
const [isPending, startTransition] = useTransition();
const selectTab = (tab: Tab) => startTransition(() => setActiveTab(tab));
```

---

## Re-render profiling before memoization

React DevTools Profiler → record the slow interaction → find which components re-render and
why → fix the *cause* (state too high in the tree, unstable context value, missing selector)
before reaching for `React.memo`. Memoization rules live in `refs/react-patterns.md`.

Common structural fixes that beat memo:

```tsx
// WRONG — state in the layout re-renders the entire app per keystroke
function App() {
  const [search, setSearch] = useState('');
  return (<><SearchBox value={search} onChange={setSearch} /><HeavyTree /></>);
}

// CORRECT — push state down into the component that uses it
function App() {
  return (<><SearchSection /><HeavyTree /></>);
}
```

---

## Images and fonts

```tsx
// WRONG — bare img: full-size original, no lazy loading, layout shift
<img src="/hero.png" />

// CORRECT — next/image: srcset, WebP/AVIF, lazy load, reserved space
import Image from 'next/image';
<Image src="/hero.png" alt="Dashboard preview" width={1200} height={600} priority />
```

`priority` only on the LCP image (above the fold); everything else lazy-loads by default.

```ts
// CORRECT — next/font: self-hosted, preloaded, zero layout shift via size-adjust
import { Inter } from 'next/font/google';
const inter = Inter({ subsets: ['latin'], display: 'swap' });
```

In Vite SPAs: `<link rel="preload">` the primary font, `font-display: swap`, WOFF2 only.

---

## Bundle analysis and import hygiene

```bash
npx vite-bundle-visualizer            # Vite
ANALYZE=true next build               # with @next/bundle-analyzer
```

```ts
// WRONG — namespace import defeats tree-shaking in poorly-flagged packages
import * as _ from 'lodash';
import moment from 'moment';                  // 300 KB, not tree-shakeable

// CORRECT — named imports from ESM packages; lighter alternatives
import { debounce } from 'lodash-es';
import { formatDistance } from 'date-fns';
```

Check bundlephobia/pkg-size before adopting a dependency; prefer platform APIs (`Intl`,
`structuredClone`, `URLSearchParams`) over libraries.

---

## Third-party scripts

Analytics, chat widgets, and tag managers are the top INP killers — they contend for the main
thread during hydration.

```tsx
// WRONG — synchronous script in <head> blocks first paint
<script src="https://widget.example.com/chat.js" />

// CORRECT — Next.js: deferred until idle
import Script from 'next/script';
<Script src="https://widget.example.com/chat.js" strategy="lazyOnload" />
```

---

## Virtualize long lists

Rendering 10,000 DOM rows is a layout/memory problem no memoization fixes. Past ~200 rows,
virtualize with **TanStack Virtual** — render only the visible window.

```tsx
const virtualizer = useVirtualizer({
  count: rows.length,
  getScrollElement: () => scrollRef.current,
  estimateSize: () => 48,
});
```
