# Auditline report

**Scope:** file `sample_bad_1.py` · **Mode:** full · **Languages:** python
**Tools:** ruff: ran (no project config; `--isolated --select F,B,S,T20,BLE`) | mypy: ran (flask not installed; 3 narrowing errors after `abort()` at lines 132, 136, 149 discarded; `[return]` at line 89 merged into PY-ERR-01)
**Coverage:** all files in scope

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 4 | 3 | 1 | 1 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `sample_bad_1.py:29` PY-SEC-02: Live payment API key hardcoded in source

```python
CHARGE_API_KEY = "pk_live_7Hq2LxW9pR4tN8vZ3mK6sJ1dQ5yB0cF"
```

**Why:** the `pk_live_` key is committed with the code, so everyone with repo or image access can charge customers through the payment API. The leak happened at commit; reachability cannot lower it.
**Fix:** read it at startup: `CHARGE_API_KEY = os.environ["CHARGE_API_KEY"]`; rotate the committed key at the provider.
**Cite:** CWE-798; OWASP A07:2021 Identification and Authentication Failures
**Source:** model · confidence: high

### [blocker] `sample_bad_1.py:61` PY-SEC-01: Request email interpolated into SQL with an f-string

```python
query = f"SELECT id, name, email FROM customers WHERE email = '{email}'"
```

**Why:** `payload["email"]` (line 127) reaches the query text through `find_customer` (line 132); the only check is an `@` in the string, so any caller of `POST /billing/run` can send `x@x' OR '1'='1` and bill another customer.
**Fix:** `conn.execute("SELECT id, name, email FROM customers WHERE email = ?", (email,)).fetchone()`
**Cite:** CWE-89; OWASP A03:2021 Injection; PEP 249 (paramstyle)
**Source:** ruff (`S608`) · confidence: high

### [blocker] `sample_bad_1.py:68` PY-COR-01: Mutable default list becomes Invoice.items and accumulates across billing runs

```python
adjustments: list[LineItem] = [],
```

**Why:** `run_billing` calls `build_invoice` without `adjustments` (line 136); `Invoice(items=adjustments)` aliases the one shared default list (line 70) and line 83 appends to it, so every run bills the line items of all earlier runs in the process. Customers are overcharged on the default path.
**Fix:** `adjustments: list[LineItem] | None = None`, then `Invoice(customer_id=customer_id, items=list(adjustments or []))`
**Cite:** Python Tutorial, "Default Argument Values"; Python Programming FAQ, "Why are default values shared between objects?"
**Source:** ruff (`B006`) · confidence: high

### [blocker] `sample_bad_1.py:160` PY-SEC-03: Path traversal: ?file= joined to EXPORT_DIR without containment

```python
return send_file(os.path.join(EXPORT_DIR, name), mimetype="text/csv")
```

**Why:** `name` comes from the query string and is only checked for a `.csv` suffix; `../../` segments or an absolute path (`os.path.join` drops the base) read any `.csv` the process can open. The docstring says the admin app authenticates requests, but no gate is visible in this file.
**Fix:** `return send_from_directory(EXPORT_DIR, name, mimetype="text/csv")` (uses `safe_join`, 404 on escape)
**Cite:** CWE-22; OWASP A01:2021 Broken Access Control; Flask docs, `send_from_directory`
**Source:** model · confidence: high

### [major] `sample_bad_1.py:77` PY-PERF-01: N+1 query: one order_items SELECT per unbilled order

```python
rows = conn.execute(
    "SELECT sku, quantity, unit_price_cents FROM order_items"
    " WHERE order_id = ?",
    (order["id"],),
```

**Why:** runs on the `POST /billing/run` request path once per unbilled order; the number of orders per customer is unbounded, so request time grows with the backlog.
**Fix:** one query: `SELECT o.id, i.sku, i.quantity, i.unit_price_cents FROM orders o JOIN order_items i ON i.order_id = o.id WHERE o.customer_id = ? AND o.status = 'unbilled'`
**Cite:** CWE-1073 (excessive data resource accesses)
**Source:** model · confidence: high

### [major] `sample_bad_1.py:91` PY-COR-02: Charge sent without an idempotency key; a timed-out success is charged again

```python
response = requests.post(
    CHARGE_API_URL,
```

**Why:** if the 10 s timeout fires after the provider has taken the charge, `charge_invoice` returns `None`, the run answers 502 and the orders stay `unbilled`, so the next run charges the customer twice. Assumes the provider accepts an idempotency key, as most payment APIs do.
**Fix:** send `"Idempotency-Key": f"invoice-{invoice.customer_id}-{min(invoice.order_ids)}"` (a key derived from the orders being billed), and record the charge attempt before calling.
**Cite:** CWE-837; IETF draft-ietf-httpapi-idempotency-key-header
**Source:** model · confidence: medium

### [major] `sample_bad_1.py:102` PY-ERR-01: Charge failures swallowed by except Exception: pass

```python
except Exception:
    pass
```

**Why:** on the money path, a network error, an HTTP error and a succeeded charge with an unexpected body all become an implicit `None` with no log, so failed and possibly-charged runs look the same.
**Fix:** `except requests.RequestException as err: logger.exception("charge failed for customer %s", invoice.customer_id); raise ChargeError from err`
**Cite:** CWE-390; CWE-396; PEP 8, "Programming Recommendations"
**Source:** ruff (`S110`, `BLE001`) · confidence: high

### [minor] `sample_bad_1.py:137` PY-DIFF-01: Leftover debug print of the invoice on the request path

```python
print("DEBUG invoice", invoice)
```

**Why:** runs on every `POST /billing/run` and writes the invoice to stdout outside the logger's levels and handlers; it holds SKUs, prices and an internal customer id, no secrets.
**Fix:** delete it, or `logger.debug("invoice built", extra={"customer_id": invoice.customer_id, "items": len(invoice.items)})`
**Cite:** CWE-532; PEP 282 (logging)
**Source:** ruff (`T201`) · confidence: high

### [nit] 1 nit from ruff

`sample_bad_1.py:10` PY-MAINT-01 unused `import json` (`F401`). Run `ruff check --fix`.

## Questions

Low-confidence blockers or majors, and absence-of-control items. Questions do not change the verdict.

- `sample_bad_1.py:147` — `charge_id` comes from the payment API response and is put into a file name. Can the provider ever return a value containing `/` or `..`? If so, `write_invoice_csv` writes outside `EXPORT_DIR`.

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
