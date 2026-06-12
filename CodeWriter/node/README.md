# Node.js Web Best Style — Claude Code Skill

A **Claude Code Skill** that makes the model write *idiomatic, performant, and secure* Node.js /
TypeScript backend code — not just code that runs. It auto-activates whenever Node/TS web code is
written, edited, refactored, or reviewed, and resolves "best style" from named authoritative
sources (Airbnb style guide, OWASP, Fastify docs, RFC 9457, Pino docs, TanStack/Prisma/BullMQ
docs, …) instead of improvising per task.

**Baseline:** TypeScript 5.5+ on Node.js 22 LTS, ESM only (`"type": "module"`). `camelCase` /
`PascalCase` / `UPPER_SNAKE_CASE` — JS/TS conventions only, never another language's.

## How it works

```
node/
├── SKILL.md        ← auto-activation frontmatter + 14 authoritative titles
├── refs/           ← 14 deep-knowledge files, loaded only when the task matches
└── tooling/        ← eslint.config.js, prettier.config.js, tsconfig.base.json, style-checklist.md
```

`SKILL.md` carries short, always-loaded rules (the *titles*). Each title names one ref file and
the trigger for loading it — refs are **never pre-loaded**. Every ref shows WRONG vs CORRECT
code and cites its source. Before code is declared done, it must pass the pre-ship gate.

## Installation

```bash
# Project-level
cp -r node /path/to/your-project/.claude/skills/

# User-level (all projects)
cp -r node ~/.claude/skills/
```

No further wiring — the skill activates from its frontmatter whenever Node/TS backend work
starts ("write a Node API", "refactor this route", editing `.ts`/`.mjs` files, …).

## What it covers (14 refs)

| Ref | Topics |
|---|---|
| `naming-and-modules.md` | camelCase, ESM, named exports, import ordering, `#private` fields |
| `typescript-and-types.md` | strict, verbatimModuleSyntax, unknown vs any, satisfies |
| `web-frameworks.md` | Fastify plugins, lifecycle hooks, AsyncLocalStorage, graceful shutdown |
| `security-web.md` | Helmet, CORS allowlists, Zod validation, SQL injection, CSRF, JWT rotation |
| `error-handling-web.md` | RFC 9457 Problem Details, AppError, centralized handler |
| `async-patterns.md` | Promise combinators, AbortController, streams, p-limit, floating promises |
| `logging-observability.md` | Pino, child loggers, redaction, Prometheus, OpenTelemetry |
| `config-and-secrets.md` | Zod env validation at startup, dotenv, Secret wrapper type |
| `testing-web.md` | Vitest, fastify.inject, AAA, boundary mocking |
| `performance-web.md` | Event loop discipline, worker_threads, streams, Redis caching, SWR, stampede |
| `database-and-orm.md` | Prisma vs Drizzle, transactions, N+1, migrations, pool sizing |
| `jobs-and-queues.md` | BullMQ, retry/backoff, idempotency, redlock, DLQ monitoring |
| `api-design.md` | Resource URLs, cursor pagination, versioning, OpenAPI via @fastify/swagger |
| `devops-and-containers.md` | Multi-stage Dockerfile, K8s probes, SIGTERM drain, CI/CD gate order |

## Using the tooling in a target repo

Copy the three configs into the project root as the starting configuration:

```bash
cp node/tooling/eslint.config.js node/tooling/prettier.config.js node/tooling/tsconfig.base.json  your-project/
cd your-project
npm i -D eslint typescript-eslint @eslint/js eslint-plugin-import eslint-plugin-security \
         eslint-config-prettier prettier typescript @tsconfig/node22
```

## Pre-ship gate

Before any Node/TS change is "done", these pass from the project root:

```bash
npx eslint .               # naming, floating promises, no-any, import order, security rules
npx tsc --noEmit           # strict, verbatimModuleSyntax, noUncheckedIndexedAccess
npx prettier --check .     # formatting
```

…plus the relevant sections of `tooling/style-checklist.md` (15 sections, 111 items). A failing
item is a fix, not a suggestion.
