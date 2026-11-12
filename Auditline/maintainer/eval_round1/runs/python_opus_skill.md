# Auditline report

**Scope:** files `module_a.py`, `module_b.py`, `module_c.py`, `module_e.py`, `test_module_e.py` (file scope, no diff) · **Mode:** full · **Languages:** python
**Tools:** ruff: ran (bundled fallback config) | mypy: ran (bundled fallback config, strict flags off)
**Coverage:** all files in scope

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 7 | 10 | 2 | 3 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.py:29` PY-SEC-02: Live payment API key hardcoded in source and sent as the Bearer credential

```python
CHARGE_API_KEY = "pk_live_7Hq2LxW9pR4tN8vZ3mK6sJ1dQ5yB0cF"
```

**Why:** Consequence: the key is used server-side as `Authorization: Bearer` on line 93, so it is a real charging credential (the `pk_` prefix does not make it publishable); anyone with the repo, an image or git history can charge customers. Reachability: the leak happens at commit, so it is never downgraded (X-SEV-04). ruff S105 misses it because the name holds KEY, not TOKEN/SECRET.
**Fix:** `CHARGE_API_KEY = os.environ["CHARGE_API_KEY"]` (fail fast when unset) and rotate the leaked key now; removing it from the file does not remove it from history.
**Cite:** CWE-798; OWASP A07:2021 Identification and Authentication Failures; OWASP Secrets Management Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_c.py:61` PY-SEC-01: Request email interpolated into the customer lookup SQL

```python
query = f"SELECT id, name, email FROM customers WHERE email = '{email}'"
```

**Why:** Consequence: `email` comes from the POST /billing/run JSON body (line 127) and only has to contain '@', so `x@y' OR '1'='1` returns the first customer and bills them; UNION payloads read any table. Reachability: every caller of the route; the docstring's 'admin app authenticates' is not a gate in code, and injection is never downgraded (X-SEV-04).
**Fix:** `conn.execute("SELECT id, name, email FROM customers WHERE email = ?", (email,)).fetchone()`
**Cite:** CWE-89; OWASP A03:2021 Injection; Python docs, sqlite3 (placeholders)
**Source:** ruff (S608) · confidence: high

### [blocker] `module_c.py:68` PY-COR-01: Mutable default list becomes every invoice's items, so line items leak into later customers' charges

```python
adjustments: list[LineItem] = [],
```

**Why:** Consequence: line 70 passes the shared default as `items=adjustments` and line 83 appends to it, so the one list created at import accumulates every customer's line items; the second billing run charges customer B for A's items plus B's (`total_cents` sums them, line 96). Reachability: `run_billing` calls `build_invoice(conn, customer["id"])` without the argument on every request, so it hits every run after the first in a worker (X-SEV-01 blocker: crosses requests and money).
**Fix:** `adjustments: list[LineItem] | None = None` and `Invoice(customer_id=customer_id, items=list(adjustments or []))`.
**Cite:** Python Tutorial, "Default Argument Values"; Python Programming FAQ, "Why are default values shared between objects?"; CWE-488
**Source:** ruff (B006) · confidence: high

### [blocker] `module_c.py:160` PY-SEC-03: Request file name joined into send_file path; a .csv suffix check does not contain it

```python
return send_file(os.path.join(EXPORT_DIR, name), mimetype="text/csv")
```

**Why:** Consequence: `name` is `request.args["file"]` (line 157); `../../../srv/other/x.csv` or an absolute `/home/app/data.csv` (os.path.join drops the base) reads any .csv the process can read, including other systems' exports. Reachability: no role check in code on this route; the module docstring is not a gate (X-SEV-03).
**Fix:** `return send_from_directory(EXPORT_DIR, name, mimetype="text/csv")` (safe_join, 404 on escape), or `p = (EXPORT_DIR / name).resolve()` and require `p.is_relative_to(EXPORT_DIR.resolve())`.
**Cite:** CWE-22; OWASP A01:2021 Broken Access Control; Flask docs, send_from_directory
**Source:** model · confidence: high

### [blocker] `module_e.py:52` PY-SEC-04: Stock cache keyed by SKU only, so one tenant's warehouse stock is served to other tenants

```python
cached = _stock_cache.get(sku)
```

**Why:** Consequence: `stock_levels` filters by `tenant_id` in SQL (line 57) but reads and writes `_stock_cache[sku]` (line 65) without the tenant, so for 30 s every tenant asking for a shared SKU such as `BOLT-M8` gets the first tenant's warehouse ids, on-hand counts and utilisation. Reachability: GET /inventory/stock/<sku> is open to every authenticated tenant user and polled on every storefront render (cross-tenant data, A01).
**Fix:** Key the cache by `(tenant_id, sku)`: `_stock_cache.get((tenant_id, sku))` and `_stock_cache[(tenant_id, sku)] = ...`.
**Cite:** CWE-639; CWE-524; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [blocker] `module_e.py:96` PY-COR-09: Reservation reads on_hand, checks it, then writes the computed value: concurrent checkouts oversell

```python
"UPDATE stock SET on_hand = ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ?",
(item["on_hand"] - quantity, g.user.tenant_id, warehouse_id, sku),
```

**Why:** Consequence: the SELECT on line 84 runs outside the `with conn` transaction (sqlite3 opens one only before DML), so two requests for 5 units against on_hand = 5 both pass the check on line 91 and both write 0: 10 units are held against 5 in stock; a purchase-order receipt that runs between the read and the write is overwritten too. Reachability: any tenant user at checkout, a shared stock row (blocker on stock counts).
**Fix:** Make it atomic: `UPDATE stock SET on_hand = on_hand - ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ? AND on_hand >= ?` and return 409 when `rowcount == 0`.
**Cite:** CWE-362; CWE-367; Python docs, sqlite3 (transaction control)
**Source:** model · confidence: high

### [blocker] `module_e.py:128` PY-SEC-04: Cancel route updates a reservation by id alone, so any user can cancel another tenant's hold

```python
"UPDATE reservations SET status = 'cancelled' WHERE id = ? AND status = 'held'"
```

**Why:** Consequence: `reservation_id` comes from the URL and the query has no `tenant_id` or `user_id` condition, while `g.user` is in scope; a user can walk sequential ids and cancel every tenant's checkout holds, releasing their stock. Reachability: POST /inventory/reservations/<id>/cancel is open to every authenticated user of every tenant.
**Fix:** Add `AND tenant_id = ? AND user_id = ?` with `(reservation_id, g.user.tenant_id, g.user.id)` and keep the 404 on no rows.
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; OWASP IDOR Prevention Cheat Sheet
**Source:** model · confidence: high

### [major] `module_c.py:75` PY-PERF-01: One order_items query per unbilled order inside the billing request

```python
for order in orders:
```

**Why:** Consequence: lines 77-81 run a query per order, so a customer with N unbilled orders costs N+1 round trips while the request holds the connection. Reachability: every POST /billing/run; the number of unbilled orders grows with the customer and is not bounded (X-SEV-02 major).
**Fix:** One JOIN: `SELECT o.id AS order_id, i.sku, i.quantity, i.unit_price_cents FROM orders o JOIN order_items i ON i.order_id = o.id WHERE o.customer_id = ? AND o.status = 'unbilled' ORDER BY o.id`.
**Cite:** CWE-1073; Django docs, "Database access optimization"
**Source:** model · confidence: high

### [major] `module_c.py:91` PY-COR-02: Charge POST sent without an idempotency key, so a timed-out or retried run charges twice

```python
response = requests.post(
```

**Why:** Consequence: headers on line 93 carry only Authorization; on a read timeout after the provider succeeded, the swallow on line 102 turns it into 502 `charge_failed`, the orders stay `unbilled`, and the next run (or a concurrent second request for the same customer) charges the same orders again. The same happens when `mark_billed` fails after a successful charge. Reachability: every billing run.
**Fix:** Send `"Idempotency-Key": sha256(f"{customer_id}:{order_ids}")` derived from the invoice (customer and order ids), so a retry returns the first charge.
**Cite:** CWE-837; IETF draft-ietf-httpapi-idempotency-key-header; RFC 9110 §9.2.2; Stripe API docs, "Idempotent requests"
**Source:** model · confidence: high

### [major] `module_c.py:102` PY-ERR-01: Charge failure swallowed by except Exception: pass with no log

```python
except Exception:
    pass
```

**Why:** Consequence: declines, timeouts, HTTP errors, a missing `charge_id` and programming errors all become an implicit `None` (mypy [return] on line 89 reports the missing return), the handler answers 502 and nothing is logged, so nobody can tell a decline from an outage or a charge that actually went through. Reachability: every failed charge on the money path (U1: minor raised to major).
**Fix:** `except (requests.RequestException, KeyError, ValueError) as exc: logger.exception("charge failed for customer %s", invoice.customer_id); raise ChargeError(...) from exc` and map ChargeError to 502 in the handler.
**Cite:** CWE-390; CWE-396; PEP 8, "Programming Recommendations"
**Source:** ruff (S110, BLE001) · confidence: high

### [major] `module_e.py:103` PY-COR-07: Reservation expiry stored as naive local time but compared against UTC

```python
(datetime.now() + RESERVATION_TTL).strftime(TS_FORMAT)),
```

**Why:** Consequence: `created_at` uses `_utc_now()` and `expire_stale_reservations` compares `expires_at < _utc_now()` (line 150), but `expires_at` is server-local wall time. On a host at UTC-5 every hold is already 4h45m expired and the next sweep returns its stock mid-checkout; at UTC+2 holds live 2h15m and block stock. Reachability: every reservation, whenever the host TZ is not UTC.
**Fix:** `(datetime.now(timezone.utc) + RESERVATION_TTL).strftime(TS_FORMAT)`, or compute `now` once and reuse it for both columns.
**Cite:** Python docs, datetime ("Aware and Naive Objects"); CWE-682
**Source:** ruff (DTZ005) · confidence: high

### [major] `module_e.py:121` PY-ERR-51: return inside finally discards any query error and answers 200 with an empty list

```python
return jsonify({"reservations": [dict(row) for row in rows]})
```

**Why:** Consequence: the `return` in the `finally` on line 120 cancels the exception in flight, so a locked database, a schema error or a bad ORDER BY returns `200 {"reservations": []}`: the user sees no reservations, nothing is logged and monitoring sees success. Reachability: GET /inventory/reservations for every user (C2/R1).
**Fix:** Drop the try/finally: run the query and `return jsonify(...)` after it; let errors reach the framework's 500 handler.
**Cite:** PEP 765; Python docs, "The try statement"
**Source:** ruff (B012) · confidence: high

### [major] `module_e.py:168` PY-COR-08: Purchase-order total computed from a float cost and truncated with int(), losing a cent

```python
total_cents = int(unit_cost * quantity * 100)
```

**Why:** Consequence: `unit_cost` is a JSON float; `0.29 * 3 * 100` is 86.99999999999999, so `int()` stores 86 cents instead of 87 in `purchase_orders.total_cents`, a ledger value (C1). Reachability: only `inventory_admin` users reach it, with the role check visible on line 158 (D1: blocker lowered to major), but it hits ordinary inputs on every receipt with a fractional cost. The test that would catch it is skipped (test_module_e.py:86).
**Fix:** Take the cost as integer cents (`unit_cost_cents`) or as a string and use `(Decimal(str(unit_cost)) * quantity * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)`.
**Cite:** Python docs, "Floating Point Arithmetic: Issues and Limitations" and decimal; CWE-682; CWE-1339
**Source:** model · confidence: medium

### [major] `test_module_e.py:61` PY-TEST-02: List test asserts len(...) >= 0, which can never fail

```python
assert len(response.get_json()["reservations"]) >= 0
```

**Why:** Consequence: the only test of `list_reservations` passes with an empty list, so it would survive the finally-return bug that hides errors (module_e.py:121) and a broken `user_id` scope; the name claims 'returns own reservations' but nothing checks ownership. Reachability: it is the suite's only coverage of that route.
**Fix:** Assert `len(...) == 1`, the reservation id, and add a second user's reservation that must not appear.
**Cite:** pytest docs, "Asserting with the assert statement"
**Source:** model · confidence: high

### [major] `test_module_e.py:67` PY-TEST-02: Cross-tenant cancel test asserts only that a status code exists

```python
assert response.status_code
```

**Why:** Consequence: any status is truthy, so the test passes when bob cancels alice's reservation with 200, which is exactly what module_e.py:128 does (the IDOR goes undetected). It is the only test of the tenant denial on the cancel route (auth logic).
**Fix:** `assert response.status_code == 404` and then check that alice's reservation is still `held` and the stock unchanged.
**Cite:** pytest docs, "Asserting with the assert statement"; OWASP ASVS 4.0.3 V4.1
**Source:** model · confidence: high

### [major] `test_module_e.py:81` PY-TEST-04: Tenant-scoping test mocks stock_levels, the function whose cache leaks across tenants

```python
with mock.patch.object(module_e, "stock_levels", side_effect=lambda t, _: levels if t == 10 else []):
```

**Why:** Consequence: the stub returns data by tenant, so the test checks the stub, not the SKU-only cache key in `stock_levels` (module_e.py:52) that serves tenant 10's stock to tenant 20; it is the only test of tenant scoping for stock and it hides the risk it is named after.
**Fix:** Use the real function: seed a `stock` row for tenant 10 only, GET as alice (200) then as bob, and assert bob gets 404 even after alice's call filled the cache.
**Cite:** Google Testing Blog, "Testing on the Toilet: Don't Overuse Mocks"; Python docs, unittest.mock ("Where to patch")
**Source:** model · confidence: high

### [major] `test_module_e.py:86` PY-TEST-06: Purchase-order cents test skipped with no reason, hiding the float-money bug

```python
@pytest.mark.skip
```

**Why:** Consequence: the only test of `receive_purchase_order`'s total would fail today (86 != 87, module_e.py:168); skipping it without a reason or ticket keeps the suite green while the ledger stores wrong totals.
**Fix:** Remove the skip and fix the computation, or `@pytest.mark.xfail(reason="TICKET-…: float cents", strict=True)` until it is fixed.
**Cite:** pytest docs, "Skip and xfail" (reason, strict)
**Source:** model · confidence: high

### [minor] `module_c.py:137` PY-DIFF-01: Debug print of the invoice on the billing request path

```python
print("DEBUG invoice", invoice)
```

**Why:** Consequence: every billing request writes the customer id, order ids and line items to stdout, bypassing the logger and its levels; no secret or card data is in the repr, so it stays minor. Reachability: every POST /billing/run (X-SEV-07 minor on a request path).
**Fix:** Delete it, or `logger.debug("invoice built for customer %s: %d items", invoice.customer_id, len(invoice.items))`.
**Cite:** CWE-532; OWASP Logging Cheat Sheet
**Source:** ruff (T201) · confidence: high

### [minor] `module_e.py:55` PY-ERR-06: Connection opened without with/closing, so a failed query skips conn.close()

```python
conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SECONDS)
```

**Why:** Consequence: if the execute on line 56 raises (database locked past the 5 s timeout, schema error) the `close()` on line 59 never runs and the handle lives until the traceback is collected; CPython usually frees it soon after, so the cost is contained (C3). Reachability: the storefront polls this on every render. The module's own `get_connection()` already does this correctly.
**Fix:** `with get_connection() as conn:` (or `with closing(sqlite3.connect(...)) as conn:`).
**Cite:** Python docs, contextlib.closing and "The with statement"; CWE-772
**Source:** model · confidence: medium

### [nit] 3 nits from ruff

Collapsed because ruff reports them (F401, T201): `module_b.py:175` PY-DIFF-01, `module_c.py:10` PY-MAINT-01, `module_e.py:11` PY-MAINT-01. Run `ruff check --fix` for the unused imports; replace the cron summary `print` with `logger.info`.

## Questions

None.

## Tool results dropped

- **ruff:** bundled fallback config; S608 dropped at module_b.py:122 (columns come from the REPORT_COLUMNS constant via a validated key) and module_e.py:116 (ORDER BY from the SORT_COLUMNS allowlist)
- **mypy:** bundled fallback config (strict flags off); dropped: 3 import-untyped (requests stubs not installed) and 2 no-any-return that follow from them / sqlite3 Row; 3 arg-type (module_a.py:147, 151, module_c.py:132) and 2 index (module_c.py:136, 149) because flask is untyped in the tool environment, so abort() does not narrow; 3 operator at module_e.py:163, 168 (type() membership does not narrow, the `and` guards it at runtime); [return] at module_c.py:89 merged into PY-ERR-01 at module_c.py:102

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).
