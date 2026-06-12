# TypeScript Frontend Best Style — Claude Code Skill

A **Claude Code Skill** that makes the model write *idiomatic, performant, accessible, and
secure* React/TypeScript frontend code — not just code that renders. It auto-activates whenever
frontend TS/TSX is written, edited, refactored, or reviewed, and resolves "best style" from
named authoritative sources (React docs, TypeScript handbook, TanStack docs, WCAG 2.1/2.2,
OWASP, Next.js 15 docs, …) instead of improvising per task.

It also ships a **design-cloning workflow**: give it a website URL (and ideally a screenshot)
and it extracts the site's look and feel into a reviewable design spec, then reproduces the
design as token-driven React code.

**Baseline:** TypeScript 5.5+ with React 19 (18 min), Next.js 15 App Router as the primary
target, Vite for SPAs. Strict tsconfig shared with the backend `node/` skill.

## How it works

```
typescript/
├── SKILL.md        ← auto-activation frontmatter + 15 authoritative titles
├── refs/           ← 15 deep-knowledge files, loaded only when the task matches
└── tooling/        ← eslint.config.js, prettier.config.js, tsconfig.base.json, style-checklist.md
```

`SKILL.md` carries short, always-loaded rules (the *titles*). Each title names one ref file and
the trigger for loading it — refs are **never pre-loaded**. Every ref shows WRONG vs CORRECT
code and cites its source. Before code is declared done, it must pass the pre-ship gate.

## Installation

```bash
# Project-level
cp -r typescript /path/to/your-project/.claude/skills/

# User-level (all projects)
cp -r typescript ~/.claude/skills/
```

No further wiring — the skill activates from its frontmatter whenever frontend work starts
("write a React component", "add a form", editing `.tsx` files, "clone the design of <url>", …).

## What it covers (15 refs)

| Ref | Topics |
|---|---|
| `naming-and-layout.md` | PascalCase components, `use*` hooks, feature co-location, barrels, Next.js file conventions |
| `typescript-strict.md` | strict + JSX config, `unknown` at boundaries, props/events/refs typing, `satisfies` |
| `react-patterns.md` | useEffect discipline, derived state, measured memoization, keys, error boundaries |
| `state-management.md` | Server vs UI vs shared state; TanStack Query vs Zustand/Jotai; Context limits; URL state |
| `data-fetching.md` | useQuery/useMutation, queryKey factories, staleTime, optimistic updates, infinite queries |
| `api-contracts.md` | Zod `safeParse` on every response, `apiFetch` wrapper, Problem Details, tRPC |
| `forms-and-validation.md` | React Hook Form + zodResolver, Controller, accessible errors, useFieldArray |
| `security-frontend.md` | XSS/DOMPurify, URL sanitization, CSP, no secrets in the bundle, HttpOnly tokens |
| `testing-frontend.md` | Vitest + RTL + userEvent + MSW, role queries, findBy*, vitest-axe |
| `accessibility.md` | Semantic HTML first, focus management, keyboard nav, labels, aria-live, contrast |
| `performance-frontend.md` | Code splitting, Suspense, useDeferredValue/useTransition, next/image+font, Core Web Vitals |
| `styling.md` | Tailwind vs CSS Modules, clsx/cn, design tokens, dark mode, no runtime CSS-in-JS |
| `nextjs-and-ssr.md` | RSC by default, `'use client'` boundary, caching modes, Server Actions, hydration |
| `build-and-ci.md` | `tsc --noEmit` in CI, path aliases, bundle budgets, Lighthouse CI, env validation |
| `design-cloning.md` | **Workflow ref** — see below |

## Design cloning from a reference URL

Trigger with *"clone the design of `<url>`"*, *"make it look like `<url>`"*, or attach a
screenshot to match.

| You provide | Fidelity |
|---|---|
| URL + full-page screenshot (+ one mobile-width) | **Best** — tokens from CSS, layout judgment from the image |
| URL only | Good — works well for server-rendered sites |
| Screenshot only | Visual-only — fonts approximated |

The workflow runs in three phases:

1. **Acquire** — fetch the page HTML and linked CSS. `:root` custom properties are the primary
   token source, then font links, repeated color/radius/shadow literals, and breakpoints. If the
   site is a JS-rendered empty shell or blocks fetching, the skill asks for a screenshot instead
   of guessing.
2. **Distill** — write `DESIGN_SPEC.md` into your project: token table with evidence, layout
   anatomy, component inventory, character notes, and an explicit "not recoverable" list. You
   confirm the spec before bulk generation.
3. **Generate** — tokens first (Tailwind theme / CSS variables, so you can re-skin from one
   file), then primitives, then layout — all passing the skill's own lint/type/a11y gate.

**Boundary:** it clones the *design language* only — never logos, brand names, copyrighted
images, or text. Generated output uses placeholder content, and commercial fonts are substituted
with the nearest open alternative.

## Using the tooling in a target repo

```bash
cp typescript/tooling/eslint.config.js typescript/tooling/prettier.config.js \
   typescript/tooling/tsconfig.base.json  your-project/
cd your-project
npm i -D eslint typescript-eslint @eslint/js eslint-plugin-react eslint-plugin-react-hooks \
         eslint-plugin-jsx-a11y eslint-plugin-testing-library eslint-config-prettier \
         prettier typescript @tsconfig/strictest
```

## Pre-ship gate

Before any frontend change is "done", these pass from the project root:

```bash
npx tsc --noEmit           # strict type checking, noUncheckedIndexedAccess, import type
npx eslint .               # hooks rules, jsx-a11y, no-explicit-any, floating promises
npx prettier --check .     # formatting
```

…plus the relevant sections of `tooling/style-checklist.md` (15 sections, 128 items). A failing
item is a fix, not a suggestion.
