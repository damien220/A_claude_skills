# Python Best Style — Claude Code Skill

A **Claude Code Skill** that makes the model write *idiomatic, performant, and secure* Python —
not just Python that runs. It auto-activates whenever Python is written, edited, refactored, or
reviewed, and resolves "best style" from named authoritative sources (PEP 8, PEP 257, PEP 634,
the CPython docs, OWASP, pytest docs, …) instead of improvising per task.

**Baseline:** Python 3.10–3.13. `snake_case` / `PascalCase` / `UPPER_CASE` per PEP 8 — Python
conventions only, never another language's.

## How it works

```
python/
├── SKILL.md        ← auto-activation frontmatter + 13 authoritative titles
├── refs/           ← 13 deep-knowledge files, loaded only when the task matches
└── tooling/        ← ruff.toml, mypy.ini, pyproject-snippet.toml, style-checklist.md
```

`SKILL.md` carries short, always-loaded rules (the *titles*). Each title names one ref file and
the trigger for loading it — refs are **never pre-loaded**, so the token cost per session stays
minimal. Every ref shows WRONG vs CORRECT code and cites its source, so recommendations are
traceable, not opinion. Before code is declared done, it must pass the pre-ship gate
(`tooling/style-checklist.md` + the lint/type commands below).

## Installation

```bash
# Project-level
cp -r python /path/to/your-project/.claude/skills/

# User-level (all projects)
cp -r python ~/.claude/skills/
```

No further wiring — the skill activates from its frontmatter whenever Python work starts.

## What it covers (13 refs)

| Ref | Topics |
|---|---|
| `naming-and-layout.md` | snake_case, import order, module names |
| `classes-and-data-modeling.md` | dataclass vs NamedTuple vs TypedDict vs Pydantic, Enum |
| `abstraction-interfaces-polymorphism.md` | Protocol vs ABC, singledispatch, match/case (PEP 634) |
| `typing-and-contracts.md` | Type hints, generics, mypy, 3.10–3.13 version matrix |
| `sync-async-concurrency.md` | async/await, asyncio.gather, TaskGroup, threads, multiprocessing |
| `performance-efficiency.md` | Data structures, comprehensions, profiling (cProfile/py-spy), caching, SWR, stampede |
| `error-handling.md` | Specific exceptions, chaining, EAFP, context managers |
| `api-and-secrets.md` | Secrets from env, pydantic-settings, timeouts/retries, SQL injection, pip-audit |
| `testing.md` | pytest, AAA, fixtures, parametrize, boundary mocking |
| `docs-and-comments.md` | PEP 257 docstrings, why-not-what comments |
| `packaging-and-structure.md` | src/ layout, pyproject.toml, entry points |
| `logging-and-observability.md` | Structured logging, Prometheus, OpenTelemetry |
| `devops-and-deployment.md` | Docker multi-stage (python:3.13-slim), health probes, CI gate order |

## Using the tooling in a target repo

Copy the `[tool.*]` blocks from `tooling/pyproject-snippet.toml` into the repo's
`pyproject.toml`, or point the standalone configs at it:

```bash
ruff check  --config python/tooling/ruff.toml     path/to/code   # E,F,W,I,N,UP,B,S,C4,SIM,PERF
ruff format --config python/tooling/ruff.toml     path/to/code
mypy        --config-file python/tooling/mypy.ini path/to/code   # disallow_untyped_defs etc.
```

The `N` (pep8-naming) and `S` (bandit security) rule families are load-bearing — they are what
make the skill's naming and security rules machine-enforced.

## Pre-ship gate

Before any Python change is "done":

1. `ruff check` and `ruff format --check` pass
2. `mypy` passes
3. The relevant sections of `tooling/style-checklist.md` (14 sections, 59 items) hold

A failing item is a fix, not a suggestion.
