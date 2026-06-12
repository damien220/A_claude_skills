# Design Cloning from a Reference URL — TypeScript Frontend Reference

This ref is a **workflow**, not a style rulebook: given a website URL (and/or screenshots), it
extracts the site's *look and feel* into a structured design specification, then reproduces it
with this skill's own rules (tokens per `refs/styling.md`, components per
`refs/react-patterns.md` + `refs/accessibility.md`, pages per `refs/nextjs-and-ssr.md`).

**Scope and ethics boundary (read first).** Clone the *design language* — palette, type scale,
spacing rhythm, layout anatomy, component shapes. Never copy assets: no logos, brand names,
copyrighted images, icon sets, or body text. Generated output uses placeholder content. If the
reference is a well-known brand and the target is a competing product, say so and steer toward
"inspired by", not pixel-identical trade dress. Respect robots.txt-style signals: fetch pages,
don't crawl, don't bypass auth/paywalls.

---

## Activation and inputs

Trigger phrases: *"clone the design of `<url>`"*, *"make it look like `<url>`"*, *"copy this
site's look and feel"*, *"use `<url>` as the design reference"*.

| Input provided | Fidelity | What it yields |
|---|---|---|
| URL + screenshot(s) | **Best** | Tokens from CSS **and** visual layout/spacing judgment from the image |
| URL only | Good | Tokens + structure from HTML/CSS; layout inferred from markup order |
| Screenshot only | Visual-only | Palette, type feel, layout anatomy read from the image; fonts approximated |

If the URL is provided without screenshots and the page is heavily client-rendered (fetched
HTML is a near-empty `<div id="root">`), **ask the user for a screenshot** — that single image
recovers most of what JS rendering hides. Full-page plus one mobile-width screenshot is ideal.

---

## Phase A — Acquire

Work with whatever fetch/HTTP tools the session provides; degrade gracefully.

1. **Fetch the page HTML.** Keep: `<head>` (meta `theme-color`, font `<link>`s, og:image),
   semantic structure (`header`/`nav`/`main`/`section`/`footer` order), recurring class-name
   vocabulary, inline `style` attributes, embedded `<style>` blocks.
2. **Fetch the linked stylesheets** (the `<link rel="stylesheet">` hrefs, resolved absolute).
   Highest-value targets, in order:
   - **`:root { --custom-properties }`** — modern sites publish their entire token system here;
     if present, extraction is nearly done.
   - `@font-face` / Google Fonts URLs — exact typefaces and weights.
   - Repeated color literals, `border-radius`, `box-shadow`, `max-width` containers,
     `@media` breakpoints.
   - Utility-class signatures (Tailwind's `gap-4 rounded-2xl shadow-sm`) — these *are* the
     token values.
3. **Read screenshots** (if given): overall density (airy vs dense), section rhythm, hero
   anatomy, card shapes, button character (pill/rounded/sharp), illustration vs photo style,
   light/dark default.
4. **Note what was NOT recoverable** (animations, hover states, exact imagery) — list these as
   open questions instead of inventing silently.

---

## Phase B — Distill into a Design Spec

Produce `DESIGN_SPEC.md` in the target project — the reviewable contract between extraction
and generation. **Show it to the user for confirmation before generating code** when the clone
is the main task; skip the pause only if the user asked for one-shot generation.

```markdown
# Design Spec — derived from <url> (fetched YYYY-MM-DD)

## Tokens
| Token | Value | Evidence |
|---|---|---|
| color.primary    | #0F62FE          | --cds-link-primary in :root |
| color.surface    | #FFFFFF / #161616 (dark) | body background, [data-theme] |
| font.heading     | "Söhne", sans-serif → nearest free: Inter | @font-face |
| font.body        | same, 400/16px/1.5 | body rule |
| radius.base      | 8px (cards 16px, buttons pill) | .card, .btn rules |
| shadow.card      | 0 1px 3px rgb(0 0 0 / 0.1) | .card |
| space scale      | 4-based: 4/8/16/24/40/64 | section paddings |
| breakpoints      | 640 / 1024 / 1280 | @media rules |
| container        | max-width 1200px, centered | .container |

## Layout anatomy
- Sticky translucent header: logo left, 5 links center, CTA button right
- Hero: two-column ≥1024px (copy left, media right), stacked mobile
- Alternating full-bleed sections; 3-col feature card grid
- Footer: 4 link columns + newsletter row

## Component inventory
Button (primary pill / ghost), Card (image-top, 16px radius), Navbar, Footer,
Badge, Section heading (eyebrow + h2 + sub)

## Character
Airy (generous whitespace), flat with hairline borders, large type scale,
subtle 150ms ease transitions

## Not recoverable / assumed
Hover animation details; exact photography style → using neutral placeholders
```

Font rule: if the reference uses a commercial font, name it in the spec but implement the
closest open alternative (Söhne→Inter, Circular→DM Sans, Graphik→Public Sans…) via `next/font`.

---

## Phase C — Generate

Everything generated must pass this skill's own gate — a clone is not an excuse for style-rule
violations.

1. **Tokens first** (`refs/styling.md`): emit the spec's token table as Tailwind `@theme` /
   `tailwind.config.ts` extension, or `:root` CSS variables for CSS Modules. Every component
   then consumes tokens — zero magic numbers, so the user can re-skin later by editing one file.
2. **Primitives next**: Button, Card, SectionHeading, Container — typed props
   (`refs/typescript-strict.md`), semantic elements and focus states (`refs/accessibility.md`).
3. **Layout last**: Navbar, Footer, page sections composing the primitives; Next.js Server
   Components by default, `'use client'` only on interactive leaves (`refs/nextjs-and-ssr.md`);
   `next/image` with reserved dimensions (`refs/performance-frontend.md`).
4. **Placeholder content**: neutral copy ("Your product name"), `https://placehold.co` or local
   gray-box images — never the reference site's text or imagery.
5. **Verify**: `tsc --noEmit`, `eslint .` (jsx-a11y active), then compare the rendered result
   against the screenshot/spec and iterate on visible deltas (spacing rhythm and type scale are
   the two that most often need a second pass).

```ts
// CORRECT — the extracted palette lands as tokens, not as scattered hex
// tailwind.config.ts
export default {
  theme: {
    extend: {
      colors: { primary: '#0F62FE', surface: { DEFAULT: '#FFFFFF', dark: '#161616' } },
      borderRadius: { card: '16px' },
      maxWidth: { container: '1200px' },
    },
  },
} satisfies Config;
```

```tsx
// WRONG — hex values copied inline straight from the reference CSS
<button style={{ background: '#0F62FE', borderRadius: 9999 }}>Get started</button>

// CORRECT — token-driven primitive
<Button variant="primary">Get started</Button>
```

---

## Failure modes

| Symptom | Response |
|---|---|
| Fetch blocked / 403 / bot-walled | Ask for a screenshot; never attempt to evade blocking |
| SPA returns empty HTML shell | Ask for a screenshot; salvage tokens from the CSS bundle URL if visible |
| CSS is minified utility soup with no `:root` | Derive tokens from *computed repetition* (most-frequent colors, radii, font sizes) and say the spec is inferred |
| Reference is a famous brand, target competes | Flag the trade-dress concern; deliver an "inspired" variant (same character, distinct identity) |
| User wants the site's text/images too | Decline the assets; offer placeholder structure + their own content slots |
