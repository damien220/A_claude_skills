# Auditline report

**Scope:** files `module_a.py`, `module_b.py`, `module_c.py`, `module_e.py`, `test_module_e.py` (file scope; nothing is pre-existing) · **Mode:** full · **Languages:** python
**Tools:** ruff: ran (bundled fallback config) | mypy: ran (bundled fallback config, strict flags off)
**Coverage:** all files in scope

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 7 | 10 | 4 | 3 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.py:29` PY-SEC-02: Live payment API key hardcoded in source

```python
CHARGE_API_KEY = "pk_live_7Hq2LxW9pR4tN8vZ3mK6sJ1dQ5yB0cF"
```

**Why:** Consequence C1: the literal is sent as the Bearer credential to the payment provider (line 93), so anyone with the repository, an image or a backup can create charges; the leak happened at commit and git history keeps it. Reachability is irrelevant for a committed production secret (X-SEV-04). ruff S105 misses it because the name contains KEY, not TOKEN/SECRET.
**Fix:** CHARGE_API_KEY = os.environ["CHARGE_API_KEY"] (fail fast when unset) and rotate the leaked key at the provider.
**Cite:** CWE-798; OWASP A07:2021 Identification and Authentication Failures; OWASP Secrets Management Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_c.py:61` PY-SEC-01: Request email interpolated into SQL text

```python
query = f"SELECT id, name, email FROM customers WHERE email = '{email}'"
```

**Why:** Consequence C1: `email` comes from the POST /billing/run body (line 127) and the only check is `"@" in email`, which does not neutralise injection; `x@y' OR '1'='1` matches the first customer, who is then invoiced and charged. Reachability R1: any caller of the route; the docstring's claim about authentication elsewhere is not a gate visible in code, and injection is never downgraded (X-SEV-04).
**Fix:** conn.execute("SELECT id, name, email FROM customers WHERE email = ?", (email,)).fetchone()
**Cite:** CWE-89; OWASP A03:2021 Injection; Python docs, sqlite3 (placeholders)
**Source:** ruff (S608) · confidence: high

### [blocker] `module_c.py:68` PY-COR-01: Mutable default list becomes every invoice's items, so line items accumulate across customers

```python
adjustments: list[LineItem] = [],
```

**Why:** Consequence C1: the default `[]` is created once and passed as `items=adjustments` (line 70); `invoice.items.append(...)` (line 83) then mutates that shared list. run_billing never passes `adjustments`, so the second billing run for customer B starts with customer A's line items and B is charged A's total plus their own. Reachability R1: every call to POST /billing/run, across requests, in the money path (X-SEV-01).
**Fix:** adjustments: list[LineItem] | None = None, then Invoice(customer_id=customer_id, items=list(adjustments or []))
**Cite:** Python Tutorial, "Default Argument Values"; Python Programming FAQ, "Why are default values shared between objects?"; CWE-488
**Source:** ruff (B006) · confidence: high

### [blocker] `module_c.py:160` PY-SEC-03: Request file name joined into a path and served; a .csv suffix check does not contain it

```python
return send_file(os.path.join(EXPORT_DIR, name), mimetype="text/csv")
```

**Why:** Consequence C1: `?file=../../../home/app/secrets.csv` or an absolute `/any/path/x.csv` (os.path.join discards EXPORT_DIR for an absolute name) reads any .csv the process can open, including other customers' invoice exports and data dumps. Reachability R1: no role check is visible in this file; the docstring about the admin app is not a gate in code (X-SEV-03).
**Fix:** return send_from_directory(EXPORT_DIR, name, mimetype="text/csv")  # safe_join; 404 on escape
**Cite:** CWE-22; OWASP A01:2021 Broken Access Control; Flask docs, send_from_directory
**Source:** model · confidence: high

### [blocker] `module_e.py:52` PY-SEC-04: Stock cache keyed by sku only, so one tenant's stock levels are served to another tenant

```python
cached = _stock_cache.get(sku)
```

**Why:** Consequence C1: stock_levels filters by tenant_id but reads and writes `_stock_cache` by `sku` alone (lines 52 and 65), so within 30 s tenant 20 asking for BOLT-M8 receives tenant 10's warehouses and on-hand counts (cross-tenant data exposure). Reachability R1: GET /inventory/stock/<sku> is open to every authenticated tenant user and polled on every storefront render. The tenant test mocks stock_levels away, so nothing catches it.
**Fix:** key the cache by (tenant_id, sku): `_stock_cache: dict[tuple[int, str], ...]`, `_stock_cache.get((tenant_id, sku))` and `_stock_cache[(tenant_id, sku)] = ...`
**Cite:** CWE-524; CWE-639; OWASP A01:2021 Broken Access Control; TanStack/Flask-Caching key guidance (include every input in the key)
**Source:** model · confidence: high

### [blocker] `module_e.py:96` PY-COR-09: Stock decremented from a value read earlier: concurrent reservations oversell

```python
"UPDATE stock SET on_hand = ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ?",
(item["on_hand"] - quantity, g.user.tenant_id, warehouse_id, sku),
```

**Why:** Consequence C1: on_hand is read by the SELECT at line 84 outside the write transaction, checked at line 91, and then written back as the absolute value `item["on_hand"] - quantity`. Two concurrent reservations of 4 against on_hand 5 both pass the check and both write 1: 8 units are held against 5 in stock and one decrement is lost. Reachability R1: any tenant user at checkout, a common concurrent path.
**Fix:** one atomic statement: `UPDATE stock SET on_hand = on_hand - ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ? AND on_hand >= ?` and abort(409) when rowcount == 0, inside the same transaction as the INSERT
**Cite:** CWE-362; CWE-367; PostgreSQL docs, "Explicit Locking" (atomic conditional update pattern)
**Source:** model · confidence: high

### [blocker] `module_e.py:128` PY-SEC-04: Any user can cancel any tenant's reservation by id: no tenant or owner check

```python
"UPDATE reservations SET status = 'cancelled' WHERE id = ? AND status = 'held'"
```

**Why:** Consequence C1: the UPDATE matches on `id` only, although g.user (tenant_id, id) is in scope; a user of tenant 20 who posts /inventory/reservations/<n>/cancel for sequential ids cancels tenant 10's holds and returns their stock to the pool (another tenant's data changed). Reachability R1: every authenticated user of the tenant API. The test meant to prove the denial asserts nothing (test_module_e.py:67).
**Fix:** add the scope to the statement: `... WHERE id = ? AND tenant_id = ? AND user_id = ? AND status = 'held'` with (reservation_id, g.user.tenant_id, g.user.id); keep the 404 on no rows
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; OWASP Insecure Direct Object Reference Prevention Cheat Sheet
**Source:** model · confidence: high

### [major] `module_c.py:77` PY-PERF-01: One order_items query per unbilled order inside the billing request

```python
rows = conn.execute(
    "SELECT sku, quantity, unit_price_cents FROM order_items"
```

**Why:** Consequence C2: build_invoice runs 1 + N queries, N = unbilled orders per customer, which grows without bound for customers billed rarely. Reachability R1: POST /billing/run on every call (X-SEV-02).
**Fix:** one JOIN: SELECT o.id AS order_id, i.sku, i.quantity, i.unit_price_cents FROM orders o JOIN order_items i ON i.order_id = o.id WHERE o.customer_id = ? AND o.status = 'unbilled' ORDER BY o.id
**Cite:** CWE-1073; Django docs, "Database access optimization"; SQLAlchemy docs, "Relationship Loading Techniques"
**Source:** model · confidence: high

### [major] `module_c.py:91` PY-COR-02: Charge POST sent without an idempotency key

```python
response = requests.post(
```

**Why:** Consequence C2 on money: a timeout or dropped response after the provider accepted the charge is swallowed into None (line 102), the endpoint answers 502 charge_failed and the orders stay unbilled, so the next billing run charges the same orders again. Reachability R1: every billing run; timeouts are a normal failure mode.
**Fix:** send `"Idempotency-Key": sha256(f"{invoice.customer_id}:{order_ids}")` derived from the customer and order ids, so a retry of the same invoice is deduplicated by the provider
**Cite:** CWE-837; IETF draft-ietf-httpapi-idempotency-key-header; RFC 9110 §9.2.2; Stripe API docs, "Idempotent requests"
**Source:** model · confidence: high

### [major] `module_c.py:102` PY-ERR-01: Every charge failure swallowed by except Exception: pass and turned into None

```python
except Exception:
    pass
```

**Why:** Consequence: declined cards, timeouts, provider 5xx, a missing charge_id and programming errors all become None with no log and no cause, so operators cannot tell a decline from an outage or from a charge that succeeded but timed out (mypy also reports the missing return on this path). C3 raised by U1 because it is the payment path; reachability R1 on every billing run: major (X-SEV-05).
**Fix:** catch `(requests.RequestException, KeyError, ValueError) as exc`, `logger.exception(...)` with the customer id, and `raise ChargeError(...) from exc`; let the route map ChargeError to 502
**Cite:** CWE-390; CWE-396; PEP 8, "Programming Recommendations"
**Source:** ruff (S110, BLE001, return) · confidence: high

### [major] `module_e.py:55` PY-ERR-06: Connection opened without with/closing: an exception in the query skips conn.close()

```python
conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SECONDS)
```

**Why:** Consequence C2: if the SELECT raises (database locked past the 5 s timeout, schema error), line 59 never runs and the connection and its file handle stay open until the frame and traceback are collected. Reachability R1: the comment says storefront pages poll this on every render, so failures repeat at request rate. Assumption: the failures happen under load, which is when the lock timeout fires.
**Fix:** use the module's helper: `with get_connection() as conn: rows = conn.execute(...).fetchall()` (closing() already wraps it)
**Cite:** Python docs, "The with statement" and contextlib.closing; CWE-772; CWE-404
**Source:** model · confidence: medium

### [major] `module_e.py:103` PY-COR-07: Reservation expiry stored as naive local time but compared with UTC timestamps

```python
(datetime.now() + RESERVATION_TTL).strftime(TS_FORMAT)),
```

**Why:** Consequence C2: created_at and the expiry sweep (line 150, `expires_at < _utc_now()`) use UTC, but expires_at uses local `datetime.now()`. On a host at UTC-5 every hold is written already 4h45m in the past and the next sweep releases the stock while the customer is checking out; at UTC+2 holds live 2h15m. Reachability R1: every reservation; the value decides expiry.
**Fix:** (datetime.now(timezone.utc) + RESERVATION_TTL).strftime(TS_FORMAT)
**Cite:** Python docs, datetime ("Aware and Naive Objects"); CWE-682
**Source:** ruff (DTZ005) · confidence: high

### [major] `module_e.py:121` PY-ERR-51: return inside finally discards any query error and answers 200 with an empty list

```python
return jsonify({"reservations": [dict(row) for row in rows]})
```

**Why:** Consequence C2: an OperationalError (locked database, bad column) is cancelled by the return in finally, so the client gets `{"reservations": []}` with status 200 and nothing is logged; the user sees their holds vanish and monitoring sees success. Reachability R1: GET /inventory/reservations for every user.
**Fix:** drop the try/finally: run the query, then `return jsonify(...)` after it; let errors reach the error handler (or catch sqlite3.Error, log it and return 503)
**Cite:** PEP 765; Python docs, "The try statement"
**Source:** ruff (B012) · confidence: high

### [major] `module_e.py:168` PY-COR-08: Purchase-order total computed from a float unit cost and truncated with int()

```python
total_cents = int(unit_cost * quantity * 100)
```

**Why:** Consequence C1: unit_cost may be a JSON float (line 163) and `int(0.29 * 3 * 100)` is 86, not 87, so the stored purchase_orders.total_cents is a cent short on ordinary amounts and reconciliation fails. Reachability R2: the route has a visible inventory_admin role check (line 158), so D1 lowers C1 blocker to major. The test written for exactly this case is skipped (test_module_e.py:86).
**Fix:** take the cost in cents as an int (`unit_cost_cents`), or `Decimal(str(unit_cost)) * quantity * 100` quantized with ROUND_HALF_UP before int()
**Cite:** Python docs, "Floating Point Arithmetic: Issues and Limitations" and decimal; CWE-682; CWE-1339
**Source:** model · confidence: high

### [major] `test_module_e.py:61` PY-TEST-02: List test asserts len(...) >= 0, which is always true

```python
assert len(response.get_json()["reservations"]) >= 0
```

**Why:** Consequence C2 false confidence: the only test of GET /inventory/reservations passes whatever the list holds, including another user's reservations or an empty list from the swallowed error in module_e.py:121. Reachability R1 from the code under test (every user's listing); it is the only check that the listing is scoped to the caller.
**Fix:** assert the content: `assert [r["sku"] for r in response.get_json()["reservations"]] == ["BOLT-M8"]` and that bob's listing is empty
**Cite:** pytest docs, "Asserting with the assert statement"
**Source:** model · confidence: high

### [major] `test_module_e.py:67` PY-TEST-02: Cross-tenant cancel test asserts only that a status code exists

```python
assert response.status_code
```

**Why:** Consequence C2 false confidence on authorization: `assert response.status_code` passes for 200, 404 and 500; the cancel route really lets bob cancel alice's reservation (module_e.py:128) and this test is green. Reachability R1 from the code under test (any authenticated user).
**Fix:** `assert response.status_code == 404` and then check alice's reservation is still held and stock unchanged
**Cite:** pytest docs, "Asserting with the assert statement"; OWASP ASVS 4.0.3 V4.1 (verify that access control denies)
**Source:** model · confidence: high

### [major] `test_module_e.py:81` PY-TEST-04: Tenant-scoping test patches out stock_levels, the function whose scoping is at risk

```python
with mock.patch.object(module_e, "stock_levels", side_effect=lambda t, _: levels if t == 10 else []):
```

**Why:** Consequence C2: by replacing module_e.stock_levels with a lambda, the test checks only that the route passes g.user.tenant_id; the real cache keyed by sku alone (module_e.py:52) leaks across tenants and this, the only tenant test of stock lookups, still passes. Reachability R1 from the code under test.
**Fix:** use the real function: insert stock for tenant 20 too, request as alice then bob, and assert each sees only their own warehouses
**Cite:** Google Testing Blog, "Testing on the Toilet: Don't Overuse Mocks"; Python docs, unittest.mock ("Where to patch")
**Source:** model · confidence: high

### [minor] `module_a.py:141` PY-ERR-05: A JSON array or string body makes payload.get raise and returns 500 instead of 400

```python
payload = request.get_json(silent=True) or {}
email = payload.get("email")
```

**Why:** Consequence C3: `request.get_json(silent=True) or {}` keeps any truthy non-object JSON (`[1]`, `"x"`), and `.get` then raises AttributeError, so a client mistake becomes a 500 that clients and alerting treat as a server fault. Reachability R1: any caller of POST /billing/run.
**Fix:** `if not isinstance(payload, dict): abort(400, description="expected a JSON object")` before reading fields
**Cite:** RFC 9110 §15.5.1 (400 Bad Request); RFC 9457
**Source:** model · confidence: high

### [minor] `module_c.py:126` PY-ERR-05: A JSON array or string body makes payload.get raise and returns 500 instead of 400

```python
payload = request.get_json(silent=True) or {}
email = payload.get("email")
```

**Why:** Consequence C3: a truthy non-object JSON body survives `or {}` and `.get` raises AttributeError, so a client mistake is answered with 500. Reachability R1: any caller of POST /billing/run.
**Fix:** `if not isinstance(payload, dict): abort(400, description="expected a JSON object")`
**Cite:** RFC 9110 §15.5.1 (400 Bad Request); RFC 9457
**Source:** model · confidence: high

### [minor] `module_c.py:137` PY-DIFF-01: Debug print of the whole invoice on the billing request path

```python
print("DEBUG invoice", invoice)
```

**Why:** Consequence C3: every billing run writes customer id, order ids and line items to stdout, bypassing the logger, its level and its redaction; no secret or contact PII is in the Invoice repr, so U4 does not apply. Reachability R1: every POST /billing/run (X-SEV-07: minor on a request path).
**Fix:** delete it, or `logger.debug("invoice built for customer %s with %d items", invoice.customer_id, len(invoice.items))`
**Cite:** CWE-532; OWASP Logging Cheat Sheet
**Source:** ruff (T201) · confidence: high

### [minor] `test_module_e.py:86` PY-TEST-06: Purchase-order rounding test skipped with no reason or ticket

```python
@pytest.mark.skip
```

**Why:** Consequence C2: the one test that would expose the float truncation in module_e.py:168 (0.29 x 3 must be 87 cents) never runs and the suite stays green. Reachability from the code under test is R2: the route has a visible inventory_admin check, so D1 gives C2 x R2 = minor.
**Fix:** fix the computation and remove the skip; if it must stay skipped, `@pytest.mark.xfail(reason="TICKET-…: float cost", strict=True)`
**Cite:** pytest docs, "Skip and xfail" (reason, strict)
**Source:** model · confidence: high

### [nit] 3 nits from ruff

Collapsed because ruff reports them (`F401`, `T201`) at `module_b.py:175`, `module_c.py:10`, `module_e.py:11`. Run `ruff check --fix` for the unused imports; replace the cron `print` with the logger.

## Questions

None.

## Pre-existing (not part of this change)

None (file scope).

## Dropped tool results

- **ruff:** bundled fallback config; S608 dropped at module_b.py:122 (columns come from the REPORT_COLUMNS constant, report validated against it) and module_e.py:116 (ORDER BY from the SORT_COLUMNS allowlist)
- **mypy:** bundled fallback config (strict flags off); flask and requests stubs not installed: 3 import-untyped dropped; 5 narrowing errors after abort() dropped (module_a.py:147, 151; module_c.py:132, 136, 149: abort resolves to Any and cannot narrow); 3 operator errors at module_e.py:163, 168 dropped (type(x) in (int, float) does not narrow, values are validated on lines 163-166); 2 no-any-return at module_c.py:62, 101 dropped (Any from untyped sqlite3.Row/requests JSON); [return] at module_c.py:89 merged into the swallowed-exception finding at module_c.py:102
