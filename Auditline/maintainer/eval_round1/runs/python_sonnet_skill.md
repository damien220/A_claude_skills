# Auditline report

**Scope:** files `module_a.py`, `module_b.py`, `module_c.py`, `module_e.py`, `test_module_e.py` (each reviewed at file scope) · **Mode:** full · **Languages:** python
**Tools:** ruff: ran | mypy: ran (bundled fallback config; discarded results are named in the JSON `tools[].note`)
**Coverage:** all five files in scope; `module_a.py` and `module_b.py` have no findings

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 7 | 9 | 3 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker to nit), then file, then line.

### [blocker] `module_c.py:29` PY-SEC-02: Live payment API key hardcoded in source

```python
CHARGE_API_KEY = "pk_live_7Hq2LxW9pR4tN8vZ3mK6sJ1dQ5yB0cF"
```

**Why:** A `*_live_*` credential is committed and sent as a Bearer token from server code (line 93), so anyone with the repository or an image can charge through the account. The leak happens at commit; reachability does not lower it (X-SEV-04). ruff S105-S107 miss it because the name contains neither `token` nor `secret`.
**Fix:** Read it from the environment and fail fast, as module_a does: `CHARGE_API_KEY = os.environ["CHARGE_API_KEY"]`; rotate the leaked key.
**Cite:** CWE-798; OWASP A07:2021 Identification and Authentication Failures; OWASP Secrets Management Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_c.py:61` PY-SEC-01: Customer email from the request interpolated into SQL text

```python
query = f"SELECT id, name, email FROM customers WHERE email = '{email}'"
```

**Why:** `email` comes from the JSON body of POST /billing/run (line 127); the only check is `'@' in email`, which does not neutralise injection, so `x@y' OR '1'='1` returns the first customer and `' UNION SELECT ...` reads any table. The route is open to every caller that reaches the blueprint and the result drives a charge (R1, C1).
**Fix:** Bind the value: `conn.execute("SELECT id, name, email FROM customers WHERE email = ?", (email,)).fetchone()`.
**Cite:** CWE-89; OWASP A03:2021 Injection; Python docs, sqlite3 placeholders
**Source:** ruff (S608) · confidence: high

### [blocker] `module_c.py:68` PY-COR-01: Mutable default list aliased into every invoice and appended to

```python
adjustments: list[LineItem] = [],
```

**Why:** `Invoice(customer_id=customer_id, items=adjustments)` stores the shared default list itself, then `invoice.items.append(...)` (line 83) adds each order's lines to it. The next call that omits `adjustments` starts with the previous customers' line items, so run_billing (which never passes it) charges customer N the sum of every earlier customer's unbilled items: money corruption on the default path (C1/R1, X-SEV-01).
**Fix:** Default to `None` and copy: `adjustments: list[LineItem] | None = None` ... `items=list(adjustments or [])`.
**Cite:** Python Tutorial, Default Argument Values; Python Programming FAQ, why default values are shared; CWE-488
**Source:** ruff (B006) · confidence: high

### [blocker] `module_c.py:160` PY-SEC-03: Request-controlled file name joined into a path and served; suffix check does not contain it

```python
return send_file(os.path.join(EXPORT_DIR, name), mimetype="text/csv")
```

**Why:** `name` is `request.args["file"]`; `.endswith(".csv")` is the only check, so `../../srv/app/secrets.csv` or an absolute path (which os.path.join lets replace EXPORT_DIR) reads any .csv the process can open. The docstring's claim that the admin app authenticates every request is not a gate visible in code (X-SEV-03, D1 does not apply).
**Fix:** Use `send_from_directory(EXPORT_DIR, name, mimetype="text/csv")` (safe_join, 404 on escape), as module_a does.
**Cite:** CWE-22; OWASP A01:2021 Broken Access Control; Flask docs, send_from_directory
**Source:** model · confidence: high

### [blocker] `module_e.py:52` PY-SEC-04: Process-wide stock cache keyed by sku only serves one tenant's stock to another

```python
cached = _stock_cache.get(sku)
```

**Why:** `stock_levels(tenant_id, sku)` queries by tenant and sku but caches and looks up by `sku` alone (also line 65), so within 30 seconds tenant B asking for 'BOLT-M8' receives tenant A's warehouse ids and on-hand counts. Any signed-in tenant user can trigger it (tenant auth is not a trust gate): other tenants' data on the default path (C1/R1; PY-COR-16 filed here as the security overlap).
**Fix:** Key the cache by `(tenant_id, sku)` (and copy or freeze the cached list).
**Cite:** CWE-639; CWE-524; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [blocker] `module_e.py:91` PY-COR-09: Stock checked and then overwritten with a value computed in Python (lost update, oversell)

```python
if item["on_hand"] < quantity:
```

**Why:** `on_hand` is read outside any write transaction, compared, then written back as `item["on_hand"] - quantity` (line 97). Two concurrent reservations of 3 against on_hand 5 both pass the check and both write 2, so 6 units are held from a stock of 5 and the counter is wrong afterwards (C1/R1: oversell on a stock count many users hit at once).
**Fix:** One atomic statement: `UPDATE stock SET on_hand = on_hand - ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ? AND on_hand >= ?` and abort 409 when `rowcount == 0`.
**Cite:** CWE-362; CWE-367; Python docs, sqlite3 transaction control; SQLite docs, Transactions
**Source:** model · confidence: high

### [blocker] `module_e.py:128` PY-SEC-04: Cancel updates any reservation by id with no tenant or owner filter

```python
"UPDATE reservations SET status = 'cancelled' WHERE id = ? AND status = 'held'"
```

**Why:** The route takes `reservation_id` from the URL and the query filters by id and status only; `g.user` is in scope but not used. Any signed-in user of any tenant can cancel another tenant's held reservation by enumerating ids, and `_return_to_stock` then adds the quantity back to the victim tenant's stock (C1/R1, X-SEV-04 class). The test that should catch it asserts nothing (test_module_e.py:67).
**Fix:** Scope the UPDATE by `tenant_id = ? AND user_id = ?` from `g.user` and return 404 on a miss: `WHERE id = ? AND tenant_id = ? AND user_id = ? AND status = 'held'`.
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; OWASP IDOR Prevention Cheat Sheet
**Source:** model · confidence: high

### [major] `module_c.py:77` PY-PERF-01: One order_items query per unbilled order inside a loop

```python
rows = conn.execute(
    "SELECT sku, quantity, unit_price_cents FROM order_items"
    " WHERE order_id = ?",
```

**Why:** A customer's unbilled orders are unbounded, so a request issues 1 + N queries (500 orders mean 501 round trips) on the POST /billing/run path (C2/R1, X-SEV-02).
**Fix:** One JOIN over orders and order_items filtered by customer_id and status, as module_a's build_invoice does.
**Cite:** CWE-1073; Python sqlite3 docs; X-SEV-02 in severity-and-output-format.md
**Source:** model · confidence: high

### [major] `module_c.py:93` PY-COR-02: Charge POST sent without an idempotency key while timeouts are reported as failures

```python
headers={"Authorization": f"Bearer {CHARGE_API_KEY}"},
```

**Why:** The request carries no Idempotency-Key, and a timeout is swallowed into `None` and answered with 502 (line 143), inviting a client retry; if the provider processed the first POST, the customer is charged twice (C2/R1). module_a derives the key from customer and order ids. Assumes the provider supports the header, as module_a's usage shows.
**Fix:** Add `"Idempotency-Key": sha256(f"{customer_id}:{order_ids}")` derived from the business object, not random per attempt.
**Cite:** CWE-837; RFC 9110 section 9.2.2 (POST is not idempotent); Stripe API docs, Idempotent requests
**Source:** model · confidence: medium

### [major] `module_c.py:102` PY-ERR-01: Charge failure swallowed by except Exception: pass; function returns None implicitly

```python
except Exception:
    pass
```

**Why:** Declined, timed out, malformed response and programming bugs all collapse into `None`, which run_billing turns into a bare 502 with no log (money path, raised one level by U1). A charge that succeeded at the provider but timed out locally also looks like a failure, so the caller's retry charges again. mypy also reports the missing return on this path (`return`, line 89).
**Fix:** Catch `(requests.RequestException, KeyError, ValueError)`, log with `logger.exception(...)`, and raise a typed error (as module_a's ChargeError) that run_billing handles.
**Cite:** CWE-390; CWE-396; PEP 8, Programming Recommendations
**Source:** ruff (BLE001, S110; mypy: return) · confidence: high

### [major] `module_e.py:103` PY-COR-07: Reservation expiry stored in naive local time but compared against UTC

```python
(datetime.now() + RESERVATION_TTL).strftime(TS_FORMAT)),
```

**Why:** `created_at` uses `_utc_now()` and `expire_stale_reservations` compares `expires_at < _utc_now()`, but `expires_at` is written from naive local `datetime.now()`. On a host whose zone is UTC+2 a reservation expires 2 hours late (stock held too long); on UTC-5 it expires 5 hours early and the stock is released while the buyer still holds it (C2/R1). Assumes a non-UTC host zone.
**Fix:** Use `datetime.now(timezone.utc) + RESERVATION_TTL` (or `_utc_now()` arithmetic) so stored and compared values are UTC.
**Cite:** Python docs, datetime (Aware and Naive Objects); CWE-682
**Source:** ruff (DTZ005) · confidence: medium

### [major] `module_e.py:121` PY-ERR-51: return inside finally discards the database error and answers 200 with an empty list

```python
return jsonify({"reservations": [dict(row) for row in rows]})
```

**Why:** If the query raises (locked database, missing table) the exception is cancelled by the `return` in `finally`, so the endpoint answers 200 with `[]` and the failure is neither logged nor visible to the client (C2/R1, PEP 765). It also swallows `abort()` raised in the block.
**Fix:** Remove the try/finally: let the error propagate (or catch a specific `sqlite3.Error`, log it, and return 500), and return after the `with` block.
**Cite:** PEP 765; Python docs, The try statement
**Source:** ruff (B012) · confidence: high

### [major] `module_e.py:168` PY-COR-08: Purchase-order total computed with int(float * qty * 100), truncating cents

```python
total_cents = int(unit_cost * quantity * 100)
```

**Why:** `unit_cost` is a JSON float: `int(0.29 * 3 * 100)` is 86, not 87 (0.29*3*100 = 86.99999999999999), so the stored `total_cents` in purchase_orders is short by a cent on ordinary amounts (C1). The route is behind an `inventory_admin` role check visible at line 158, so reachability is gated (D1): major rather than blocker.
**Fix:** Accept the cost as a string or integer cents and use `Decimal(str(unit_cost)) * quantity * 100` quantized with ROUND_HALF_UP, or store unit_cost_cents as an integer end to end.
**Cite:** Python docs, Floating Point Arithmetic: Issues and Limitations; Python docs, decimal; CWE-682
**Source:** model · confidence: high

### [major] `test_module_e.py:67` PY-TEST-02: Cross-tenant cancel test asserts only that the status code is truthy

```python
assert response.status_code
```

**Why:** Any HTTP status is truthy, so the test passes whether bob's cancel returns 404 or 200. It is the only test of the tenant-isolation rule on cancel, and it passes against the real IDOR at module_e.py:128 (survives the mutation 'drop the ownership check'; C2/R1 on an auth path).
**Fix:** Assert the outcome: `assert response.status_code == 404` and that alice's reservation is still `held` and stock is unchanged.
**Cite:** pytest docs, Asserting with the assert statement
**Source:** model · confidence: high

### [major] `test_module_e.py:81` PY-TEST-04: Tenant-scoping test mocks stock_levels, the function that holds the tenant filter and cache

```python
with mock.patch.object(module_e, "stock_levels", side_effect=lambda t, _: levels if t == 10 else []):
```

**Why:** The patched function is module_e's own `stock_levels`, so the 200/404 results come from the lambda, not from the SQL tenant filter or the cache; this is the only test of tenant isolation for stock and it cannot see the cross-tenant cache leak at module_e.py:52.
**Fix:** Seed rows for both tenants in the real sqlite file the fixture builds and call the endpoint for alice then bob (cache cleared by the fixture), mocking only the clock if needed.
**Cite:** Python docs, unittest.mock (Where to patch); Google Testing Blog, Don't Overuse Mocks
**Source:** model · confidence: high

### [major] `test_module_e.py:86` PY-TEST-06: Purchase-order total test skipped with no reason

```python
@pytest.mark.skip
```

**Why:** The skipped test is the only check that the purchase-order total is exact in cents, and it would fail today (the code returns 86 for 3 x 0.29): the suite is green while the money bug in module_e.py:168 stays hidden (major: skip with no reason on a test of the changed code).
**Fix:** Remove the skip so the test runs and fix the code, or use `@pytest.mark.xfail(reason="TICKET: float total", strict=True)`.
**Cite:** pytest docs, Skip and xfail
**Source:** model · confidence: high

### [minor] `module_c.py:137` PY-DIFF-01: Debug print of the invoice object on the billing request path

```python
print("DEBUG invoice", invoice)
```

**Why:** Runs on every POST /billing/run, bypasses the structured logger and its levels, and writes customer ids and amounts to stdout (C3/R1: minor on a request path, X-SEV-07). It is not a secret, so not major.
**Fix:** Delete it, or use `logger.debug("invoice built for customer %s", customer["id"])`.
**Cite:** CWE-532; OWASP Logging Cheat Sheet
**Source:** ruff (T201) · confidence: high

### [minor] `module_e.py:55` PY-ERR-06: SQLite connection in stock_levels is closed only on the happy path

```python
conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SECONDS)
```

**Why:** `conn.close()` (line 59) runs after the query with no `finally`/`closing`; an exception from `execute` or `fetchall` leaks the connection and its file handle on the storefront polling path (C3/R1). The other functions use the `get_connection()` context manager.
**Fix:** Use `with get_connection() as conn:` as the rest of the module does.
**Cite:** Python docs, contextlib.closing; Python docs, sqlite3 (closing connections)
**Source:** model · confidence: high

### [minor] `test_module_e.py:61` PY-TEST-02: List test asserts len(...) >= 0, which is always true

```python
assert len(response.get_json()["reservations"]) >= 0
```

**Why:** A list length is never negative, so the test passes with an empty list, including after the endpoint swallows a database error (module_e.py:121) or returns other users' rows; it never checks that alice's own reservation is listed.
**Fix:** Assert the content: `ids = [r["id"] for r in ...]` and that the id returned by `reserve()` is in it (and bob's is not).
**Cite:** pytest docs, Asserting with the assert statement
**Source:** model · confidence: high

### [nit] 2 nits from ruff (F401)

Collapsed because ruff reports them: `module_c.py:10` PY-MAINT-01 (unused import json); `module_e.py:11` PY-MAINT-01 (unused import uuid). Run `ruff check --fix`.

## Questions

None.

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
