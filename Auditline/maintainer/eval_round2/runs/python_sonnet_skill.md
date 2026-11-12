# Auditline report

**Scope:** files `module_a.py`, `module_b.py`, `module_c.py`, `module_e.py`, `test_module_e.py` (file scope, each reviewed on its own) · **Mode:** full · **Languages:** python
**Tools:** ruff: ran (bundled fallback config) | mypy: ran (bundled fallback config; 11 results discarded, see notes)
**Coverage:** all 5 files in scope. `module_a.py` has no findings; `module_b.py` has one nit.

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 7 | 12 | 1 | 3 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.py:29` PY-SEC-02: Live payment API key hardcoded in source

```python
CHARGE_API_KEY = "pk_live_7Hq2LxW9pR4tN8vZ3mK6sJ1dQ5yB0cF"
```

**Why:** CHARGE_API_KEY is a literal pk_live_ credential sent as the Bearer token on line 93 from server code, so it is a secret. Anyone with the repository or an image holds a key that can charge customers; git history keeps it after deletion. ruff S105 does not match the name, so no tool reports it.
**Fix:** CHARGE_API_KEY = os.environ["CHARGE_API_KEY"] (fails fast when unset) and rotate the leaked key.
**Cite:** CWE-798; OWASP A07:2021 Identification and Authentication Failures; OWASP Secrets Management Cheat Sheet
**Source:** model · confidence: high

### [blocker] `module_c.py:61` PY-SEC-01: Customer email interpolated into SQL text (injection)

```python
query = f"SELECT id, name, email FROM customers WHERE email = '{email}'"
```

**Why:** email comes from the JSON body of POST /billing/run and only has to contain '@' (line 128), so "x' OR '1'='1@a" returns an arbitrary customer row and the run bills that customer; a UNION payload reads any table. Format validation does not neutralise injection and no visible gate limits who calls it.
**Fix:** conn.execute("SELECT id, name, email FROM customers WHERE email = ?", (email,)).fetchone()
**Cite:** CWE-89; OWASP A03:2021 Injection; Python docs, sqlite3 ("How to use placeholders to bind values in SQL queries")
**Source:** ruff (S608) · confidence: high

### [blocker] `module_c.py:68` PY-COR-01: Mutable default list is aliased into every invoice and mutated, mixing customers' line items

```python
adjustments: list[LineItem] = [],
```

**Why:** Consequence: adjustments=[] is evaluated once; line 70 stores that same list as invoice.items and line 83 appends every order line to it. run_billing (line 136) calls build_invoice without adjustments, so each request's items stay in the shared default, and the next customer's invoice total (and charge on line 96) includes all earlier customers' items. Reachability: the default path of every billing run. Money is charged wrongly across customers.
**Fix:** adjustments: list[LineItem] | None = None, then items=list(adjustments or []) when building the Invoice.
**Cite:** Python Programming FAQ, "Why are default values shared between objects?"; Python Tutorial, "Default Argument Values"; CWE-488
**Source:** ruff (B006) · confidence: high

### [blocker] `module_c.py:160` PY-SEC-03: Request-controlled filename joined to export dir and sent; .csv suffix check does not contain the path

```python
return send_file(os.path.join(EXPORT_DIR, name), mimetype="text/csv")
```

**Why:** name comes from ?file= and only has to end with .csv. os.path.join(EXPORT_DIR, name) discards EXPORT_DIR for an absolute name (/etc/app/secrets.csv) and "../" segments climb out of it, so any .csv the process can read is returned. The module docstring says the admin app authenticates every request, but that is a claim about another file, not a gate visible in code (D1 does not apply).
**Fix:** return send_from_directory(EXPORT_DIR, name, mimetype="text/csv") (rejects names that resolve outside the directory), as module_a.py does.
**Cite:** CWE-22; OWASP A01:2021 Broken Access Control; Flask docs, send_from_directory; Werkzeug docs, safe_join
**Source:** model · confidence: high

### [blocker] `module_e.py:52` PY-COR-16: Stock cache keyed by sku only; result depends on tenant_id, so tenants are served each other's stock

```python
cached = _stock_cache.get(sku)
```

**Why:** stock_levels(tenant_id, sku) reads rows WHERE tenant_id = ? AND sku = ?, but the cache key (lines 52 and 65) is only sku. The first tenant to request BOLT-M8 fills _stock_cache and for the next 30 seconds every other tenant gets that tenant's warehouses and on_hand counts from GET /inventory/stock/<sku>. Cross-tenant data exposure on the default path.
**Fix:** Key the cache by (tenant_id, sku): _stock_cache.get((tenant_id, sku)) and store under the same tuple.
**Cite:** CWE-524; CWE-488; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [blocker] `module_e.py:96` PY-COR-09: Reservation reads on_hand, checks it, then writes an absolute value computed in Python (lost update, oversell)

```python
"UPDATE stock SET on_hand = ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ?",
(item["on_hand"] - quantity, g.user.tenant_id, warehouse_id, sku),
```

**Why:** The SELECT (line 84) and the UPDATE (line 96) are separate statements and sqlite3 does not open a transaction for the SELECT, so two concurrent reservations of 3 against on_hand = 5 both pass the check on line 91 and both write 2, instead of rejecting the second: stock is oversold and the stock count is wrong. Many users can hit this endpoint at once (R1) and it is the stock count (C1).
**Fix:** Make it one atomic statement: UPDATE stock SET on_hand = on_hand - ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ? AND on_hand >= ?, and abort(409) when rowcount == 0.
**Cite:** CWE-362; CWE-367; Python docs, sqlite3 ("Transaction control")
**Source:** model · confidence: high

### [blocker] `module_e.py:128` PY-SEC-04: Cancel by reservation id with no ownership or tenant check

```python
"UPDATE reservations SET status = 'cancelled' WHERE id = ? AND status = 'held'"
```

**Why:** POST /inventory/reservations/<id>/cancel updates the row matching only id and status = 'held'. Any signed-in user of any tenant can cancel any other tenant's or user's reservation by guessing sequential ids, which also returns that tenant's stock via _return_to_stock. The list endpoint scopes by user_id (line 117) and the rest of the file by tenant_id, so the check is clearly intended and missing here.
**Fix:** Add AND tenant_id = ? AND user_id = ? to the UPDATE (bind g.user.tenant_id and g.user.id) and return 404 for rows that do not match.
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [major] `module_c.py:77` PY-PERF-01: One order_items query per unbilled order inside build_invoice

```python
rows = conn.execute(
    "SELECT sku, quantity, unit_price_cents FROM order_items"
```

**Why:** The loop over orders issues a query per order on a request path (POST /billing/run). Unbilled orders per customer grow without bound, so latency and DB load grow linearly with that count while the invoice is built. module_a.py shows the single-JOIN form.
**Fix:** Fetch all lines in one query: JOIN orders and order_items WHERE o.customer_id = ? AND o.status = 'unbilled' ORDER BY o.id.
**Cite:** CWE-1073; Python docs, sqlite3
**Source:** model · confidence: high

### [major] `module_c.py:91` PY-COR-02: Charge POST sent without an Idempotency-Key

```python
response = requests.post(
```

**Why:** Assuming the caller re-runs POST /billing/run after a 502 (the endpoint answers charge_failed for a timeout on line 98 even if the provider processed the charge), the orders are still 'unbilled', so the retry charges the customer a second time. The same happens if mark_billed fails after a successful charge. module_a.py derives a key from customer and order ids.
**Fix:** Add an Idempotency-Key header derived from customer_id and order_ids (not random per attempt).
**Cite:** CWE-837; RFC 9110 section 9.2.2 (POST is not idempotent); Stripe API docs, "Idempotent requests"
**Source:** model · confidence: medium

### [major] `module_c.py:102` PY-ERR-01: Charge failure swallowed by except Exception: pass; function falls through returning None

```python
except Exception:
    pass
```

**Why:** On the billing path, a declined card, a timeout, a bad JSON body or a coding bug all become None with no log, so the caller answers 502 charge_failed without any record of why, and a timeout after a provider-side success looks identical to a decline (see the missing idempotency key). Money path raises the level (U1). mypy [return] reports the implicit fall-through return on line 89 for the same defect.
**Fix:** Catch (requests.RequestException, KeyError, ValueError), log with logger.exception, and raise a ChargeError the caller handles, as module_a.py does.
**Cite:** CWE-390; CWE-396; PEP 8, "Programming Recommendations"
**Source:** ruff (S110, BLE001, return) · confidence: high

### [major] `module_e.py:55` PY-ERR-06: Connection closed only on the success path in stock_levels

```python
conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT_SECONDS)
rows = conn.execute(
    "SELECT warehouse_id, on_hand, capacity FROM stock WHERE tenant_id = ? AND sku = ?", (tenant_id, sku)
).fetchall()
conn.close()
```

**Why:** If conn.execute raises (database is locked after the 5 s timeout, a missing table), conn.close() on line 59 is skipped and the handle leaks until garbage collection. This runs on every storefront stock lookup (R1), so repeated failures exhaust file handles and locks. The module already has get_connection() with closing().
**Fix:** Use `with get_connection() as conn:` around the query, as the other handlers do.
**Cite:** Python docs, "The with statement" and contextlib.closing; CWE-772; CWE-404
**Source:** model · confidence: high

### [major] `module_e.py:103` PY-COR-07: Reservation expiry stored in naive local time but compared against UTC

```python
(datetime.now() + RESERVATION_TTL).strftime(TS_FORMAT)),
```

**Why:** expires_at is written as datetime.now() (server local time) while created_at uses _utc_now() and expire_stale_reservations (line 148) compares expires_at < _utc_now() in UTC. On any server not set to UTC the 15-minute hold is off by the UTC offset: west of UTC (UTC-5) a new hold is already past its expiry, so the next expiry run releases the stock at once; east of UTC (UTC+2) a hold lasts 2h15m instead of 15 minutes, so stock stays locked.
**Fix:** Use datetime.now(timezone.utc) (or _utc_now() + RESERVATION_TTL via a helper) so every stored timestamp is UTC.
**Cite:** Python docs, datetime ("Aware and Naive Objects"); CWE-682
**Source:** ruff (DTZ005) · confidence: high

### [major] `module_e.py:121` PY-ERR-51: return inside finally in list_reservations silences every exception

```python
return jsonify({"reservations": [dict(row) for row in rows]})
```

**Why:** The finally block returns a 200 response even when the query raises (locked database, missing table), so the error is discarded and the client receives an empty reservations list as if the user had none, with nothing logged. It also overrides any HTTP exception raised in the try. Python 3.14 makes this a SyntaxWarning under PEP 765.
**Fix:** Drop the try/finally: run the query inside the with block and return jsonify(...) after it; let errors propagate to the app's handler.
**Cite:** PEP 765 (disallow return, break and continue that exit a finally block); Python docs, "The try statement"
**Source:** ruff (B012) · confidence: high

### [major] `module_e.py:158` PY-TEST-07: Admin-only purchase-order endpoint has no test that proves a non-admin is rejected

```python
if "inventory_admin" not in g.user.roles:
```

**Why:** Assuming test_module_e.py is the only test file (no other test references /inventory/purchase-orders), the 403 branch is never exercised, and the only purchase-order test is skipped without a reason (test_module_e.py:86), so neither the denial nor the happy path is verified. Removing the role check would leave the suite green.
**Fix:** Add a test posting as alice or bob to /inventory/purchase-orders and asserting status_code == 403, and un-skip the admin test.
**Cite:** OWASP ASVS 4.0.3 V4.1 (verify access control denies); pytest docs, "How to parametrize fixtures and test functions"
**Source:** model · confidence: medium

### [major] `module_e.py:168` PY-COR-08: Purchase-order total computed with float arithmetic and truncated with int()

```python
total_cents = int(unit_cost * quantity * 100)
```

**Why:** Failing input: unit_cost = 0.29, quantity = 3 gives 0.29 * 3 * 100 = 86.99999999999999, so int() stores total_cents = 86 instead of 87 (line 175 writes it to purchase_orders). The stored amounts are off by a cent on ordinary values. Reachable only by inventory_admin users (line 158 gate, D1), which is why this is major rather than blocker.
**Fix:** Parse unit_cost as Decimal(str(unit_cost)) (or require integer cents) and compute (Decimal * quantity * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP).
**Cite:** Python docs, "Floating Point Arithmetic: Issues and Limitations" and decimal; CWE-682; CWE-1339
**Source:** model · confidence: high

### [major] `test_module_e.py:61` PY-TEST-02: Assertion len(...) >= 0 is always true; list test cannot fail

```python
assert len(response.get_json()["reservations"]) >= 0
```

**Why:** len() is never negative, so this passes when the endpoint returns nothing, someone else's reservations or (see module_e.py:121) swallows an error and returns an empty list. It is the only test of list_reservations, which scopes data to the current user, so it gives false confidence about the query. Survives: returning [] instead of the user's rows.
**Fix:** Assert the actual content: that the list holds exactly the reservation alice just created, and that bob's call returns none of alice's.
**Cite:** pytest docs, "Asserting with the assert statement"
**Source:** model · confidence: high

### [major] `test_module_e.py:67` PY-TEST-02: assert response.status_code is truthy for any status; cross-tenant cancel test checks nothing

```python
assert response.status_code
```

**Why:** Any HTTP status (200, 404, 500) is non-zero and passes. The test is named test_cancel_rejects_other_tenants_reservation, so it is the only check of the tenant boundary on cancel, and it would pass while module_e.py:128 lets bob cancel alice's reservation (a blocker). Survives: any implementation, including the current vulnerable one.
**Fix:** assert response.status_code == 404 (or 403) and then check that alice's reservation is still 'held' and stock unchanged.
**Cite:** pytest docs, "Asserting with the assert statement"
**Source:** model · confidence: high

### [major] `test_module_e.py:81` PY-TEST-04: stock_levels, the unit under test, is replaced by a lambda that implements the tenant scoping

```python
with mock.patch.object(module_e, "stock_levels", side_effect=lambda t, _: levels if t == 10 else []):
```

**Why:** mock.patch.object(module_e, "stock_levels", side_effect=lambda t, _: ... if t == 10 else []) means the assertions only prove the mock's own tenant check; the real stock_levels, its SQL and its cache never run. That is exactly the code that leaks stock across tenants (module_e.py:52), so the mock hides the risk. Survives: the cache bug.
**Fix:** Call the real endpoint with seeded data for two tenants (the fixture already has tenant 10 stock) and assert bob gets 404 after alice has populated the cache.
**Cite:** pytest docs, unittest.mock (patch the boundary, not the unit under test)
**Source:** model · confidence: high

### [major] `test_module_e.py:86` PY-TEST-06: Test of the purchase-order total is skipped with no reason

```python
@pytest.mark.skip
```

**Why:** @pytest.mark.skip without a reason or ticket disables the only test of the money calculation. With unit_cost 0.29 and quantity 3 it would fail (86 != 87, see module_e.py:168), so the skip is hiding the defect. The skipif on line 70 shows the project's own convention of giving a reason.
**Fix:** Remove the skip and fix the total, or use @pytest.mark.xfail(reason="TICKET-...: float rounding", strict=True) with an owner.
**Cite:** pytest docs, "Skip and xfail" (reason, strict)
**Source:** model · confidence: high

### [minor] `module_c.py:137` PY-DIFF-01: Debug print of the invoice left in the billing request handler

```python
print("DEBUG invoice", invoice)
```

**Why:** print("DEBUG invoice", invoice) runs on every POST /billing/run, bypassing the structured logger and writing customer ids and line items to stdout. No secrets are printed, so minor rather than major.
**Fix:** Delete it, or use logger.debug with only customer_id.
**Cite:** CWE-532; CWE-489 (active debug code)
**Source:** ruff (T201) · confidence: high

### [nit] 3 nits

Collapsed because ruff reports them: `module_b.py:175` T201, `module_c.py:10` F401, `module_e.py:11` F401. Run `ruff check --fix` for the unused imports and replace the `print` with a logger call if wanted.

## Questions

None.

## Pre-existing (not part of this change)

None (file scope: nothing is pre-existing).

## Notes on tool results

- **ruff:** bundled fallback config. Dropped S608 at module_b.py:122 (columns come from the constant REPORT_COLUMNS allowlist, report validated against it) and at module_e.py:116 (ORDER BY value comes from the SORT_COLUMNS allowlist).
- **mypy:** bundled fallback config (strict flags off). Discarded 11 results: flask not resolvable so abort() does not narrow (module_a.py:147,151; module_c.py:132,136,149 are false positives), type(x) in (int, float) guard not understood (module_e.py:163,168), missing requests stubs (3), no-any-return noise (module_c.py:62,101). The [return] result at module_c.py:89 is merged into the PY-ERR-01 finding.
