# CodeWriter

A collection of language-specific **Claude Code Skills** that bias code generation toward
*idiomatic, performant, and secure* code — not "code that merely works." Instead of letting the
model improvise style on every task, each skill consults a curated, source-grounded style
knowledge base and applies the right pattern for the task at hand.

## Design

- **Skill, not subagent.** Each language ships a `SKILL.md` that auto-activates whenever that
  language is being written, edited, refactored, or reviewed. Deep knowledge lives in `refs/` and
  is loaded **on demand** (progressive disclosure), so per-session token cost stays minimal.
- **Idiomatic-per-language, not uniform.** "Best style" is resolved from the named authoritative
  source *per language* — PEP 8 for Python, Airbnb + TS handbook for Node, React/Next.js docs +
  WCAG for the frontend — with the rationale stated. Python uses `snake_case`; JS/TS uses
  `camelCase`. Conventions never bleed across languages.
- **Enforceable, not just advised.** Each language ships linter/type-checker configs plus a
  pre-ship checklist, so "best style" is *verifiable*, not opinion.
- **Self-contained units.** Each language is a top-level directory with its own
  `SKILL.md` + `refs/` + `tooling/`. No shared code across language dirs.

## Skills

| Skill | Directory | Status | Scope |
|---|---|---|---|
| **Python** | [`python/`](python/) | **Complete** — 13 refs, 13 titles | Idiomatic Python 3.10–3.13: naming, dataclasses/Pydantic, typing, async, performance, error handling, secrets, testing, packaging, logging, Docker/CI |
| **Node.js (backend)** | [`node/`](node/) | **Complete** — 14 refs, 14 titles | TypeScript 5.5+ on Node 22: ESM, strict TS, Fastify, OWASP security, RFC 9457 errors, Pino, Vitest, Prisma/Drizzle, BullMQ, API design, Docker/K8s |
| **TypeScript (frontend)** | [`typescript/`](typescript/) | **Complete** — 15 refs, 15 titles | React 19 + Next.js 15 App Router: hooks discipline, TanStack Query, Zod contracts, React Hook Form, XSS/CSP, RTL+MSW testing, WCAG a11y, Core Web Vitals — plus a **design-cloning workflow** that reproduces a reference website's look and feel from a URL/screenshot |
| C++ | `cpp/` | Planned | — |

Each skill directory has its own README with full details and usage. The authoritative
specs and roadmaps live in `plan-python.md`, `plan-node.md`, and `plan-typescript.md`.

## How a skill works

```
<lang>/
├── SKILL.md        ← entry point: YAML frontmatter (auto-activation triggers) +
│                      short authoritative titles, each with a "Read refs/x.md when: …" line
├── refs/           ← deep knowledge, one topic per file: WRONG vs CORRECT examples,
│                      comparison tables, every rule grounded in a cited source
└── tooling/        ← linter/formatter/type-checker configs + style-checklist.md
                       (the pre-ship gate generated code is validated against)
```

The titles in `SKILL.md` are the always-loaded summary. A ref is read **only** when the current
task matches its trigger — never pre-emptively. Before code is declared done, it must pass the
skill's pre-ship gate (lint + typecheck + format + checklist).

## Installation

Copy the skill directory (or all of them) into your Claude Code skills location:

```bash
# Project-level (this repo only)
cp -r python node typescript /path/to/your-project/.claude/skills/

# User-level (all your projects)
cp -r python node typescript ~/.claude/skills/
```

The skill auto-activates from its frontmatter description — no further wiring needed. Write,
edit, refactor, or review code in the language and the skill engages.

## Adding a language

Copy an existing skill directory as the template, rewrite `SKILL.md`'s frontmatter and titles
for that language's idioms, replace `refs/` and `tooling/` with that ecosystem's standards, and
add a `plan-<lang>.md`. Keep the unit self-contained — no imports across language dirs.
