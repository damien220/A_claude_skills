# Accessibility — TypeScript Frontend Reference

Grounded in **WCAG 2.1/2.2 (AA)**, the **MDN ARIA docs**, the **A11y Project checklist**, and
**Deque axe-core rules**. Enforced by `eslint-plugin-jsx-a11y` (recommended) in CI and
`vitest-axe` in tests.

---

## Semantic HTML first — ARIA is the fallback, not the tool

The first rule of ARIA: don't use ARIA when a native element exists. Native elements ship
keyboard handling, focus behavior, and screen-reader semantics for free; ARIA only *labels*
things — it implements nothing.

```tsx
// WRONG — div soup: no keyboard access, no focus, no role, three ARIA patches needed
<div className="btn" onClick={handleSave}>Save</div>
<div className="nav">...</div>
```

```tsx
// CORRECT — native elements; zero ARIA required
<button type="button" onClick={handleSave}>Save</button>
<nav aria-label="Primary">...</nav>
<main>...</main>
```

| Job | Element — never a styled `<div>` |
|---|---|
| Performs an action | `<button>` |
| Navigates somewhere | `<a href>` |
| Page landmark regions | `<header>` `<nav>` `<main>` `<footer>` `<aside>` |
| Standalone content unit | `<article>`, `<section aria-labelledby=…>` |
| Form grouping | `<fieldset>` + `<legend>` |

`<div onClick>` fails four ways at once: not focusable, not keyboard-operable, no role
announced, no `:focus-visible`. `jsx-a11y/click-events-have-key-events` and
`no-static-element-interactions` flag it.

---

## Buttons vs links

Action → `<button>`; navigation → `<a href>`. A `<a onClick>` without `href` is invisible to
keyboards; a `<button>` that navigates breaks open-in-new-tab and middle-click.

```tsx
// WRONG
<a onClick={() => router.push('/settings')}>Settings</a>
<button onClick={() => router.push('/settings')}>Settings</button>

// CORRECT — Next.js
<Link href="/settings">Settings</Link>
```

---

## Focus management in modals and dialogs

WCAG 2.4.3 (Focus Order). A dialog must: move focus inside on open, trap Tab within itself,
close on Escape, and return focus to the trigger on close. Don't hand-roll this — use the
native `<dialog>` element or a primitive library (Radix UI, Headless UI, React Aria) that
implements the APG dialog pattern.

```tsx
// WRONG — focus stays behind the overlay; Tab walks the hidden page; Esc does nothing
{isOpen && <div className="overlay"><div className="modal">{children}</div></div>}
```

```tsx
// CORRECT — Radix implements trap, Escape, and focus return per WAI-ARIA APG
import * as Dialog from '@radix-ui/react-dialog';

<Dialog.Root open={isOpen} onOpenChange={setIsOpen}>
  <Dialog.Portal>
    <Dialog.Overlay className="overlay" />
    <Dialog.Content aria-describedby="dlg-desc">
      <Dialog.Title>Delete project?</Dialog.Title>
      <Dialog.Description id="dlg-desc">This cannot be undone.</Dialog.Description>
      <Dialog.Close asChild><button>Cancel</button></Dialog.Close>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
```

After client-side route changes, move focus to the new page's `<h1>` (or a skip target) so
screen readers announce the navigation.

---

## Keyboard navigation

Everything mouse-operable must be keyboard-operable (WCAG 2.1.1). Tab reaches it; Enter/Space
activates it; arrow keys move within composite widgets (menus, tabs, listboxes) per the
WAI-ARIA Authoring Practices.

```tsx
// WRONG — positive tabindex creates a parallel tab order that fights the DOM order
<input tabIndex={3} />
```

| `tabIndex` | Meaning |
|---|---|
| (none) | Native order — the default, almost always right |
| `0` | Adds a non-native element to the tab order (rare; you now owe it key handlers) |
| `-1` | Programmatically focusable only (skip targets, dialog containers) |
| `> 0` | Never |

Focus must be *visible* (WCAG 2.4.7): style `:focus-visible`, and never `outline: none`
without a replacement.

---

## Images and media

```tsx
// WRONG — missing alt (announced as filename); redundant alt
<img src="/chart.png" />
<img src="/logo.svg" alt="image of logo" />

// CORRECT — informative: describe content; decorative: empty alt
<img src="/q3-chart.png" alt="Q3 revenue grew 18% to €2.4M" />
<img src="/divider.svg" alt="" />
<Image src={product.image} alt={product.name} width={300} height={200} />
```

---

## Forms

Every input needs a programmatic label — placeholder text is not a label (disappears on input,
low contrast, not announced reliably). See `refs/forms-and-validation.md` for the full
error-display pattern (`aria-invalid`, `aria-describedby`, `role="alert"`).

```tsx
// WRONG
<input placeholder="Search" />

// CORRECT — visible label, or aria-label when design forbids one
<label htmlFor="q">Search</label>
<input id="q" type="search" />

<input type="search" aria-label="Search products" />
```

---

## Dynamic announcements — `aria-live`

Content that changes without focus moving (toasts, async errors, "3 results found") must be in
a live region or screen readers never hear it.

```tsx
// CORRECT — role="alert" = assertive; polite for non-urgent counts
<p role="alert">{errorMessage}</p>
<p aria-live="polite">{results.length} results</p>
```

The live region must exist in the DOM *before* the message appears — conditionally render the
text inside it, not the region itself.

---

## Color and contrast

- Text contrast ≥ **4.5:1**; large text (≥ 24px / 18.7px bold) ≥ **3:1**; UI controls ≥ 3:1
  (WCAG 1.4.3, 1.4.11).
- Color is never the only signal (WCAG 1.4.1): error states get an icon/text, not just a red
  border; links in prose are underlined, not merely colored.
- Tokens (`refs/styling.md`) should encode passing pairs so per-component checks are rare.

---

## CI enforcement

| Layer | Tool |
|---|---|
| Lint | `eslint-plugin-jsx-a11y` recommended rules (in `tooling/eslint.config.js`) |
| Unit tests | `vitest-axe` on every interactive component |
| E2E / staging | Lighthouse CI accessibility score budget (see `refs/build-and-ci.md`) |

Automated checks catch ~40% of WCAG issues (Deque) — keyboard-walk new UI manually: Tab
through, operate everything, check focus visibility, close dialogs with Escape.
