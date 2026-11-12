# Auditline report

**Scope:** file `module_a.py`, `module_b.py`, `module_c.py`, `module_e.py`, `test_module_e.py` · **Mode:** full · **Languages:** python
**Tools:** ruff: ran (bundled fallback config) · mypy: ran (bundled fallback config)
**Coverage:** all 5 files in scope (file scope, nothing pre-existing). Dropped tool results and reasons are in the JSON `tools[].note`.

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 8 | 8 | 2 | 2 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.py:29` PY-SEC-02: Live payment API key hardcoded in source

```python
CHARGE_API_KEY = "pk_live_7Hq2LxW9pR4tN8vZ3mK6sJ1dQ5yB0cF"
```

**Why:** A live credential is committed in source and is sent as the Bearer token on every charge (line 93). Anyone with the repository or its history holds it; the leak happens at commit, so reachability does not lower it (X-SEV-04). The key must be treated as compromised.
**Fix:** CHARGE_API_KEY = os.environ["CHARGE_API_KEY"]  (as module_a.py does, fails fast at startup); rotate the leaked key
**Cite:** CWE-798; CWE-200; OWASP A07:2021 Identification and Authentication Failures
**Source:** model · confidence: high

### [blocker] `module_c.py:61` PY-SEC-01: Customer email interpolated into SQL text

```python
query = f"SELECT id, name, email FROM customers WHERE email = '{email}'"
```

**Why:** The email from the POST /billing/run body reaches the SQL text. The only check is that it contains '@', so an input such as x@' OR '1'='1 returns rows the caller should not see. The auth claim in the docstring is not a gate in this module (D1 does not apply) and X-SEV-04 keeps injection at blocker.
**Fix:** conn.execute("SELECT id, name, email FROM customers WHERE email = ?", (email,)).fetchone()  (module_a.py already uses find_customer_id this way)
**Cite:** CWE-89; OWASP A03:2021 Injection
**Source:** ruff (S608) · confidence: high

### [blocker] `module_c.py:68` PY-COR-01: Mutable default list shared by every build_invoice call

```python
    adjustments: list[LineItem] = [],
```

**Why:** Invoice(items=adjustments) aliases the single default list, and build_invoice appends every order line to invoice.items (line 88). Each billing run that omits adjustments leaves its line items in the default, so later runs in the same process (a long-lived Flask worker) bill for earlier customers' items. Data crosses billing runs: X-SEV-01 blocker.
**Fix:** adjustments: list[LineItem] | None = None, then items=list(adjustments or [])
**Cite:** Python Tutorial, Default Argument Values; Python Programming FAQ, Why are default values shared between objects?; CWE-488
**Source:** ruff (B006) · confidence: high

### [blocker] `module_c.py:160` PY-SEC-03: Export download path built with os.path.join from a request argument

```python
    return send_file(os.path.join(EXPORT_DIR, name), mimetype="text/csv")
```

**Why:** The file query argument only has to end in .csv. os.path.join lets an absolute name replace EXPORT_DIR and '../' segments escape it, so any .csv readable by the process can be downloaded. No visible role check exists in the module; the docstring's claim about the admin app does not count (D1). X-SEV-03 blocker.
**Fix:** return send_from_directory(EXPORT_DIR, name, mimetype="text/csv")  (as module_a.py does; it rejects names that resolve outside EXPORT_DIR)
**Cite:** CWE-22; OWASP A01:2021 Broken Access Control; Flask docs, send_from_directory
**Source:** model · confidence: high

### [blocker] `module_e.py:52` PY-COR-16: Stock cache keyed by SKU only, so one tenant is served another tenant's levels

```python
    cached = _stock_cache.get(sku)
```

**Why:** The cache key is sku alone, but stock_levels reads tenant-scoped rows. For 30 seconds after one tenant loads a SKU, any other tenant asking for the same SKU gets the first tenant's warehouse levels (get_stock on line 71 does no further check). Another tenant's data is served: blocker (C1/R1). The test at test_module_e.py:81 mocks stock_levels, the function that holds the bug, so it cannot catch it.
**Fix:** Key the cache on (tenant_id, sku): _stock_cache.get((tenant_id, sku)) and store under the same tuple
**Cite:** TanStack/Flask caching guidance on keys: CWE-524; CWE-200; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [blocker] `module_e.py:96` PY-COR-09: Stock decremented from a value read earlier, so concurrent reservations oversell

```python
                "UPDATE stock SET on_hand = ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ?",
                (item["on_hand"] - quantity, g.user.tenant_id, warehouse_id, sku),
```

**Why:** on_hand is read on lines 84-88 with no write lock, then the UPDATE writes a value computed in Python. Assuming two reservations for the last units overlap (the default path under load), both pass the check on line 91, and the second write overwrites the first, so the stock is oversold and held units vanish. Assumption stated: the overlap needs concurrent requests on the same warehouse line. Data corruption on a common path: blocker (C1/R1).
**Fix:** One atomic statement: UPDATE stock SET on_hand = on_hand - ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ? AND on_hand >= ?; abort 409 when rowcount is 0
**Cite:** CWE-362; CWE-367; SQLite docs, BEGIN TRANSACTION (IMMEDIATE)
**Source:** model · confidence: medium

### [blocker] `module_e.py:128` PY-SEC-04: Reservation cancelled by id without an ownership check

```python
            "UPDATE reservations SET status = 'cancelled' WHERE id = ? AND status = 'held'"
            " RETURNING tenant_id, warehouse_id, sku, quantity",
```

**Why:** The cancel route takes reservation_id from the URL and updates by id alone. Any signed-in user of any tenant can cancel another user's hold, which also returns the stock to that warehouse (line 134). Reachability is every authenticated user (R1). The test that should catch this asserts only a truthy status (test_module_e.py:67).
**Fix:** Add AND user_id = ? AND tenant_id = ? with (reservation_id, g.user.id, g.user.tenant_id) and return 404 on no match (list_reservations already scopes by user_id)
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control; OWASP IDOR Prevention Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_e.py:168` PY-COR-08: Purchase-order cost converted to cents through float arithmetic

```python
    total_cents = int(unit_cost * quantity * 100)
```

**Why:** The float product is truncated: 0.29 * 3 * 100 evaluates to 86.99999999999999, and int() stores 86 cents in purchase_orders.total_cents, a financial record. The skipped test (test_module_e.py:86) expects 87. Floats stored in a ledger-like table are blocker by the rubric.
**Fix:** Convert from a Decimal built from str, quantize with ROUND_HALF_UP, or accept unit_cost_cents as an integer from the client
**Cite:** Python docs, Floating Point Arithmetic: Issues and Limitations; decimal module; CWE-682
**Source:** model · confidence: high

### [major] `module_c.py:77` PY-PERF-01: One query per order inside the invoice loop

```python
        rows = conn.execute(
            "SELECT sku, quantity, unit_price_cents FROM order_items"
            " WHERE order_id = ?",
            (order["id"],),
        ).fetchall()
```

**Why:** build_invoice runs a query for every unbilled order of the customer on the POST /run request path. The order count per customer is unbounded, so latency grows with it (X-SEV-02, major). module_a.py does the same work in one JOIN.
**Fix:** One JOIN over orders and order_items for the customer, as build_invoice in module_a.py
**Cite:** CWE-1073; SQLAlchemy docs, Relationship Loading Techniques; Django docs, Database access optimization
**Source:** model · confidence: high

### [major] `module_c.py:93` PY-COR-02: Charge sent without an Idempotency-Key

```python
            headers={"Authorization": f"Bearer {CHARGE_API_KEY}"},
```

**Why:** Assuming the provider may charge and the local write then fails (mark_billed on line 145 raises after a successful charge), the orders stay unbilled and the next POST /run sends a second charge with no key the provider can dedupe. module_a.py derives a key from the order ids for exactly this case. Money is at stake (C1) but the trigger is a failure window, so major with medium confidence.
**Fix:** headers={"Authorization": f"Bearer {CHARGE_API_KEY}", "Idempotency-Key": idempotency_key(invoice)}  (as module_a.py)
**Cite:** CWE-837; IETF draft-ietf-httpapi-idempotency-key-header; Stripe API docs, Idempotent requests
**Source:** model · confidence: medium

### [major] `module_c.py:102` PY-ERR-01: Charge failure swallowed: except Exception returns None with no log

```python
    except Exception:
        pass
```

**Why:** This is the money path (U1, X-SEV-05). Every failure (timeout, 5xx, malformed response, missing charge_id) becomes None with no log and no chained exception. run_billing then returns charge_failed, and its logger.exception on line 158 is never reached because nothing propagates. The reason for the failed charge is lost. mypy [return] on line 89 is the same defect (the function falls through to None) and is merged here.
**Fix:** except (requests.RequestException, KeyError, ValueError) as exc: raise ChargeError(...) from exc, as module_a.py does, and let run_billing catch ChargeError
**Cite:** CWE-390; CWE-396; PEP 8, Programming Recommendations
**Source:** ruff (S110, BLE001) · confidence: high

### [major] `module_e.py:103` PY-COR-07: Reservation expiry stored in naive local time, compared against UTC

```python
                 (datetime.now() + RESERVATION_TTL).strftime(TS_FORMAT)),
```

**Why:** datetime.now() is naive local time, while created_at and expire_stale_reservations (line 150) use UTC. On any host not set to UTC, every hold expires early (stock released while held) or late (stock locked) by the UTC offset. This affects every reservation: C2 wrong result on the common path. ruff DTZ005 is the tool signal.
**Fix:** datetime.now(timezone.utc) + RESERVATION_TTL, formatted with TS_FORMAT, the same as _utc_now()
**Cite:** Python docs, datetime (aware vs naive); CWE-682
**Source:** ruff (DTZ005) · confidence: high

### [major] `module_e.py:120` PY-ERR-51: return in finally swallows a failed query and reports an empty list

```python
        finally:
            return jsonify({"reservations": [dict(row) for row in rows]})
```

**Why:** If the SELECT raises, the return in finally discards the exception and the handler answers 200 with reservations: [] and logs nothing. A failed read looks like an empty account (C2 wrong result, R1). ruff B012 is the tool signal.
**Fix:** Remove the try/finally and return after the with-block; let the exception propagate to the error handler
**Cite:** PEP 765 (disallow return, break and continue that exit a finally block); Python docs, The try statement
**Source:** ruff (B012) · confidence: high

### [major] `test_module_e.py:67` PY-TEST-02: Cross-tenant cancel test asserts a truthy status, so it cannot fail

```python
    assert response.status_code
```

**Why:** Any non-zero status passes. This is the only test of the cancel ownership path (module_e.py:128), and it passes whether the cancel is allowed or rejected, so the blocker above is not covered: major (false confidence on auth logic).
**Fix:** assert response.status_code == 404 and assert the reservation is still status 'held'
**Cite:** pytest docs, Asserting with the assert statement
**Source:** model · confidence: high

### [major] `test_module_e.py:81` PY-TEST-04: Tenant-isolation test mocks the function that contains the leak

```python
    with mock.patch.object(module_e, "stock_levels", side_effect=lambda t, _: levels if t == 10 else []):
```

**Why:** The test replaces stock_levels itself, so the cache in that function (module_e.py:52) is never exercised. It is the only test of tenant scoping and it cannot detect the cross-tenant leak: major (C2).
**Fix:** Test stock_levels against a real temporary database with two tenants, and clear _stock_cache between calls
**Cite:** Python docs, unittest.mock, Where to patch; Google Testing Blog, Don't Overuse Mocks
**Source:** model · confidence: high

### [major] `test_module_e.py:86` PY-TEST-06: Money test skipped without a reason

```python
@pytest.mark.skip
```

**Why:** The only test of purchase-order cent exactness is skipped with no reason or ticket, so the float bug at module_e.py:168 is not caught. Skip with no reason on a test of changed code: major.
**Fix:** Fix the arithmetic (module_e.py:168) and remove the skip, or use xfail(reason='TICKET: ...', strict=True) until it is fixed
**Cite:** pytest docs, Skip and xfail (reason, strict)
**Source:** model · confidence: high

### [minor] `module_c.py:137` PY-DIFF-01: Debug print on the billing request path

```python
        print("DEBUG invoice", invoice)
```

**Why:** print on the POST /run path bypasses the structured logger and writes every line item to stdout on each run (X-SEV-07: minor on a request path).
**Fix:** Delete it, or logger.debug(...) with the invoice id only
**Cite:** CWE-532; OWASP Logging Cheat Sheet
**Source:** ruff (T201) · confidence: high

### [minor] `test_module_e.py:61` PY-TEST-02: List test asserts a count that is always true

```python
    assert len(response.get_json()["reservations"]) >= 0
```

**Why:** The assertion holds for an empty list, so the test never checks that the reservation made on line 58 is listed.
**Fix:** assert len(...) == 1 and the returned sku is BOLT-M8
**Cite:** pytest docs, Asserting with the assert statement
**Source:** model · confidence: high

### [nit] 2 nits from ruff (F401)

Collapsed because ruff reports them (`F401`). Run `ruff check --fix`. The unused imports are `json` in module_c.py:10 and `uuid` in module_e.py:11.

## Questions

None.

## Pre-existing (not part of this change)

None (file scope).

