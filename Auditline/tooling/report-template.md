# Auditline report

**Scope:** {diff against `<base>` | file `<path>`} · **Mode:** {full | security-only} · **Languages:** {python, node, typescript}
**Tools:** {ruff: ran | mypy: skipped (not installed) | …; "model-only review" when every tool was skipped}
**Coverage:** {all files in scope | reviewed N of M files; skipped: …}

## Verdict: {approve | approve with nits | request changes}

| blocker | major | minor | nit |
|---|---|---|---|
| {n} | {n} | {n} | {n} |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `src/app/db.py:42` PY-SEC-01: SQL built by string formatting

```python
cursor.execute(f"SELECT * FROM users WHERE name = '{name}'")
```

**Why:** user input reaches the query text, so `name = "x' OR '1'='1"` returns every row.
**Fix:** pass parameters separately: `cursor.execute("SELECT * FROM users WHERE name = %s", (name,))`
**Cite:** CWE-89; OWASP A03:2021 Injection
**Source:** model · confidence: high

### [nit] 7 formatting nits

Collapsed because ruff reports them (`E501`, `I001`). Run `ruff check --fix`.

## Questions

Low-confidence blockers or majors, and absence-of-control items, go here, not above. Questions do not change the verdict.

- `src/app/jobs.py:88` — Is `retry()` ever called concurrently? If so the counter update is a race.

## Pre-existing (not part of this change)

Only blockers, each labelled. Excluded from the counts and the verdict.
