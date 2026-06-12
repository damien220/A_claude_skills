# Styling — TypeScript Frontend Reference

Grounded in the **CSS Modules docs**, the **Tailwind CSS docs**, and **Josh Comeau — CSS for
JavaScript Developers**. One approach per project — mixing systems produces specificity wars
and double design-token sources.

---

## Choosing the approach

| | **Tailwind CSS** | **CSS Modules** | Runtime CSS-in-JS |
|---|---|---|---|
| Scoping | Utility classes (no collision by design) | Hashed class names | Generated classes |
| Runtime cost | Zero | Zero | Style injection + serialization per render |
| Design system enforcement | Built-in (tokens in config) | Manual (CSS variables) | Manual |
| RSC / streaming compat | ✅ | ✅ | ❌ most libraries require `'use client'` |
| Best for | Product teams, design-system-driven UI | Gradual adoption, CSS-heavy teams | Avoid in new projects |

**Default recommendation: Tailwind** for new Next.js apps (token enforcement, co-location,
zero runtime). **CSS Modules** when the team prefers real CSS files. **Avoid runtime CSS-in-JS**
(styled-components, Emotion) in new projects — incompatible with Server Components and adds
runtime overhead (source: Next.js docs "CSS-in-JS"; both libraries require client components).

---

## No styling logic in inline `style`

Inline styles bypass the design system, can't be themed, have the highest specificity, and
defeat CSP `style-src` hardening. Conditional appearance = conditional *classes*.

```tsx
// WRONG — logic and magic values in the style prop
<p style={{ color: isError ? '#d32f2f' : '#1a1a1a', marginTop: 12 }}>{msg}</p>
```

```tsx
// CORRECT — Tailwind + the cn() helper (clsx + tailwind-merge)
import { cn } from '@/lib/cn';
<p className={cn('mt-3 text-neutral-900', isError && 'text-red-600')}>{msg}</p>
```

```tsx
// CORRECT — CSS Modules + clsx
import clsx from 'clsx';
import styles from './Message.module.css';
<p className={clsx(styles.message, isError && styles.error)}>{msg}</p>
```

```ts
// lib/cn.ts — the standard helper (shadcn/ui convention)
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
```

The only legitimate inline styles are *truly dynamic values* (drag positions, computed chart
coordinates, user-chosen colors) — ideally piped through a CSS variable:

```tsx
<div className={styles.bar} style={{ '--progress': `${pct}%` } as React.CSSProperties} />
```

---

## Design tokens — no magic numbers

Every color, spacing step, radius, shadow, and breakpoint comes from a token. Tailwind: the
`theme` config *is* the token set. CSS Modules: CSS custom properties in `:root`.

```css
/* WRONG — orphan values nobody can theme or audit */
.card { padding: 13px; border-radius: 7px; color: #343a40; }
```

```css
/* CORRECT — globals.css holds tokens only */
:root {
  --color-text: oklch(0.25 0.01 260);
  --color-surface: oklch(0.98 0 0);
  --color-danger: oklch(0.55 0.2 25);
  --space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem; --space-4: 1rem;
  --radius-md: 0.5rem;
}
.card { padding: var(--space-4); border-radius: var(--radius-md); color: var(--color-text); }
```

```ts
// CORRECT — Tailwind v4: tokens via @theme in CSS; v3: tailwind.config.ts theme.extend
// Components then use bg-surface, text-danger, rounded-md — never arbitrary values
// like p-[13px] except as a deliberate, commented exception.
```

---

## Dark mode — CSS-driven, flash-free

Theme is a CSS concern: `prefers-color-scheme` for "follow the OS", a `data-theme` attribute
for a user toggle. A JS-only toggle flashes the wrong theme before hydration (FOUC).

```css
/* CORRECT — tokens flip; components never know */
:root { --color-bg: white; --color-text: black; }
[data-theme='dark'] { --color-bg: #111; --color-text: #eee; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) { --color-bg: #111; --color-text: #eee; }
}
```

```tsx
// CORRECT — Next.js: next-themes sets the attribute pre-paint via an inline script
import { ThemeProvider } from 'next-themes';
<ThemeProvider attribute="data-theme">{children}</ThemeProvider>
```

---

## Global styles — resets and tokens only

`globals.css` contains: the reset, token definitions, and base typography. Component styles
live in the component's module / utility classes. Global tag selectors (`div`, `button`,
deep descendant chains) create specificity conflicts every component must out-shout.

```css
/* WRONG in globals.css */
button { background: blue; color: white; }
.sidebar ul li a { ... }
```

---

## Responsive — mobile-first, token breakpoints

Base styles target the smallest screen; `min-width` queries (Tailwind `sm:` `md:` `lg:`) add
complexity upward. Never mix `min-` and `max-width` directions in one component.

```tsx
// CORRECT — Tailwind is mobile-first by design
<div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
```

Container queries (`@container`, Tailwind `@container/@md:`) are now baseline — prefer them for
components that adapt to their *slot* rather than the viewport (cards in both sidebar and main).

---

## Co-location and naming

- CSS Module sits next to its component: `UserCard.tsx` + `UserCard.module.css`.
- Class names inside modules are `camelCase` (`styles.errorText`) so they're valid TS property
  access.
- Don't reach into another component's module — shared appearance becomes a shared component
  or a token, not a cross-import.
