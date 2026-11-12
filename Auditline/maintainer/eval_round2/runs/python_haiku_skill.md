# Auditline report

**Scope:** file (module_a.py, module_b.py, module_c.py, module_e.py, test_module_e.py) · **Mode:** full · **Languages:** python
**Tools:** ruff: ran (bundled fallback config) · mypy: ran (bundled fallback config, strict flags off)
**Coverage:** all 5 files in scope; the inventory test fixture `inventory_schema.sql` is not in the bundle and was not reviewed.

## Verdict: request changes

| blocker | major | minor | nit |
|---|---|---|---|
| 7 | 7 | 4 | 3 |

Counts exclude pre-existing findings and questions; they equal `summary` in the JSON report.

## Findings

Sorted by severity (blocker → nit), then file, then line.

### [blocker] `module_c.py:29` PY-SEC-02: Live payment API key hardcoded in source

```python
CHARGE_API_KEY = "pk_live_7Hq2LxW9pR4tN8vZ3mK6sJ1dQ5yB0cF"
```

**Why:** The key is sent as a Bearer credential from server code (line 93), so the `pk_` prefix does not make it public. Anyone with the repository or its history can charge customers. Ruff S105-S107 do not match this name.
**Fix:** Read it from the environment as module_a does: `CHARGE_API_KEY = os.environ["CHARGE_API_KEY"]`, then rotate the leaked key.
**Cite:** CWE-798; OWASP A07:2021 Identification and Authentication Failures
**Source:** model · confidence: high

### [blocker] `module_c.py:61` PY-SEC-01: SQL text built from the request email by f-string

```python
query = f"SELECT id, name, email FROM customers WHERE email = '{email}'"
```

**Why:** The email comes from the JSON body of POST /billing/run and is checked only for an '@' (line 128). Any caller who reaches the route can close the quote and run arbitrary SQL against the billing tables.
**Fix:** Bind the value: `conn.execute("SELECT id, name, email FROM customers WHERE email = ?", (email,)).fetchone()`.
**Cite:** CWE-89; OWASP A03:2021 Injection
**Source:** ruff (S608) · confidence: high

### [blocker] `module_c.py:68` PY-COR-01: Mutable default list shared across billing calls

```python
adjustments: list[LineItem] = [],
```

**Why:** Line 70 passes the default list into `Invoice(items=adjustments)` and line 83 appends each billed line to `invoice.items`, so the default list keeps growing across calls. The next customer's invoice total (`amount_cents`, line 96) includes earlier customers' lines. That is a wrong charge on the common path (C1 money, R1 open; X-SEV-01).
**Fix:** Default to `None` and copy: `adjustments: list[LineItem] | None = None` and `Invoice(customer_id=customer_id, items=list(adjustments or []))`.
**Cite:** Python Programming FAQ, "Why are default values shared between objects?"; CWE-488
**Source:** ruff (B006) · confidence: high

### [blocker] `module_c.py:160` PY-SEC-03: Request-controlled file name reaches send_file through os.path.join

```python
return send_file(os.path.join(EXPORT_DIR, name), mimetype="text/csv")
```

**Why:** An absolute `name` makes `os.path.join` discard EXPORT_DIR, and `..` segments escape it. The `.csv` suffix check (line 158) does not contain the path. No authorization gate is visible in this file; the docstring claim is not a gate (D1). Any caller can read any *.csv on the host.
**Fix:** Use `send_from_directory(EXPORT_DIR, name, mimetype="text/csv")`, as module_a does.
**Cite:** CWE-22; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [blocker] `module_e.py:52` PY-SEC-04: Stock cache keyed by SKU only serves one tenant's levels to another

```python
cached = _stock_cache.get(sku)
```

**Why:** The cache is written with key `sku` alone (line 65), and the tenant is not part of the key. Within the 30 s TTL, a request from tenant 20 for a SKU that tenant 10 has just read receives tenant 10's warehouse levels. Any signed-in user can read another tenant's stock on the request path (C1 exposure, R1). The test at test_module_e.py:81 does not catch it.
**Fix:** Key the cache by tenant: `_stock_cache[(tenant_id, sku)]`, and read it with the same key.
**Cite:** CWE-639; CWE-200; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [blocker] `module_e.py:96` PY-COR-09: Stock read, checked, then overwritten with an absolute value

```python
"UPDATE stock SET on_hand = ? WHERE tenant_id = ? AND warehouse_id = ? AND sku = ?",
```

**Why:** `on_hand` is read at line 86 outside any write lock, checked at line 91, and written back as `on_hand - quantity` (line 97). Two concurrent reservations both read 5 and both write 3, so one hold is lost and the stock is oversold. Blocker because many customers can reserve the same SKU at once (the single-writer exception does not apply). Confidence medium: it needs concurrent requests.
**Fix:** Make the decrement atomic and check the row count: `UPDATE stock SET on_hand = on_hand - ? WHERE ... AND on_hand >= ?`, then abort 409 when the count is 0.
**Cite:** CWE-362; CWE-367; PostgreSQL docs, "Explicit Locking"
**Source:** model · confidence: medium

### [blocker] `module_e.py:128` PY-SEC-04: Reservation cancelled by id without an ownership check

```python
"UPDATE reservations SET status = 'cancelled' WHERE id = ? AND status = 'held'"
```

**Why:** The UPDATE filters only on the reservation id. Nothing compares `g.user.tenant_id` or `g.user.id`, so any authenticated user in any tenant can cancel any open hold, and the stock is returned to the warehouse (the tenant test at test_module_e.py:66 shows bob cancelling alice's hold).
**Fix:** Scope the statement to the caller: add `AND tenant_id = ? AND user_id = ?` with `g.user.tenant_id, g.user.id`, and return 404 on a miss.
**Cite:** CWE-639; CWE-862; OWASP A01:2021 Broken Access Control
**Source:** model · confidence: high

### [major] `module_c.py:91` PY-COR-02: Charge POST without an idempotency key

```python
response = requests.post(
```

**Why:** No Idempotency-Key is sent (module_a derives one from the invoice). After a timeout or a lost response, charge_invoice returns None and the operator sees charge_failed. Running /billing/run again creates a second charge while the first may have succeeded. The diff adds no automatic retry, so the default is major (C2/R1). Confidence medium: the second charge needs an operator retry.
**Fix:** Send `Idempotency-Key: idempotency_key(invoice)` with the same helper module_a uses, so a retry is deduplicated by the provider.
**Cite:** CWE-837; IETF draft-ietf-httpapi-idempotency-key-header; Stripe API docs, "Idempotent requests"
**Source:** model · confidence: medium

### [major] `module_c.py:102` PY-ERR-01: Charge failure swallowed by except Exception: pass

```python
except Exception:
    pass
```

**Why:** On the billing path a failed charge becomes None with no log (mypy also reports the missing return at line 89, the same defect). run_billing then answers charge_failed, but a charge the provider accepted before a timeout or a bad response leaves no trace for operators (X-SEV-05 U1: money path, major).
**Fix:** Catch the specific errors (`requests.RequestException`, `KeyError`, `ValueError`), raise `ChargeError` from them and log in run_billing, as module_a does.
**Cite:** CWE-390; CWE-396
**Source:** ruff (S110, BLE001) · confidence: high

### [major] `module_e.py:103` PY-COR-07: Reservation expiry stored as naive local time

```python
(datetime.now() + RESERVATION_TTL).strftime(TS_FORMAT)),
```

**Why:** expires_at is stored as naive local time, while created_at (line 102) and the expiry sweep (line 150) use UTC. On a host that is not on UTC, a hold ends early (stock returns while the customer is still checking out, so it can be sold twice) or late (stock stays locked). Wrong stock on a common path; confidence medium because it depends on the host time zone.
**Fix:** Store the UTC instant: `datetime.now(timezone.utc) + RESERVATION_TTL`, as `_utc_now()` does.
**Cite:** Python docs, datetime ("Aware and Naive Objects"); PEP 615
**Source:** ruff (DTZ005) · confidence: medium

### [major] `module_e.py:121` PY-ERR-51: return inside finally swallows the query error

```python
return jsonify({"reservations": [dict(row) for row in rows]})
```

**Why:** The return in `finally` discards any exception raised by the query at lines 115-119. A database failure therefore answers HTTP 200 with an empty `reservations` list, which a client cannot tell from a user with no holds (C2 wrong result, R1).
**Fix:** Move the return after the try block and let the error propagate, or drop the try and return from the body.
**Cite:** PEP 765; Python docs, "The try statement"
**Source:** ruff (B012) · confidence: high

### [major] `module_e.py:168` PY-COR-08: Float unit cost truncated by int() when computing cents

```python
total_cents = int(unit_cost * quantity * 100)
```

**Why:** unit_cost is a float and int() truncates the binary product: 0.29 * 3 * 100 is 86.99999999999999 and gives 86, not 87 (checked in CPython). The value is stored in purchase_orders.total_cents (line 178). The route is behind the visible role check at line 158, so the reach is gated (D1) and the defect stays major.
**Fix:** Convert from decimal text: `int((Decimal(str(unit_cost)) * quantity * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))`, or accept integer cents from the client.
**Cite:** Python docs, "Floating Point Arithmetic: Issues and Limitations" and decimal; CWE-682
**Source:** model · confidence: high

### [major] `test_module_e.py:67` PY-TEST-02: Cross-tenant cancel test asserts a truthy status code

```python
assert response.status_code
```

**Why:** Any status code is truthy, so the test passes whatever the cancel route does. It is the only check of the cross-tenant cancel path, and the defect at module_e.py:128 passes it.
**Fix:** Assert the outcome: `assert response.status_code == 404`, and check that alice's reservation is still held.
**Cite:** pytest docs, "Asserting with the assert statement"
**Source:** model · confidence: high

### [major] `test_module_e.py:81` PY-TEST-04: Tenant-scoping test patches the function it is meant to test

```python
with mock.patch.object(module_e, "stock_levels", side_effect=lambda t, _: levels if t == 10 else []):
```

**Why:** The test replaces `stock_levels`, the function whose tenant scoping it claims to test, with a stub that filters by tenant itself, so the test verifies the mock. The cache at module_e.py:52 passes it. It is the only tenant-scoping test (C2 exposure, R1).
**Fix:** Remove the patch. Seed stock for two tenants in the fixture (the DB path is already monkeypatched) and assert each tenant's response.
**Cite:** Google Testing Blog, "Testing on the Toilet: Don't Overuse Mocks"; Python docs, unittest.mock "Where to patch"
**Source:** model · confidence: high

### [minor] `module_b.py:68` PY-COR-07: Schedule time that does not exist on the DST spring-forward day fires late

```python
candidate = datetime.combine(local_day, local_time, tzinfo=tz)
```

**Why:** A local_time inside the spring-forward gap (for example 02:30 in America/New_York) is built with fold=0, which ZoneInfo resolves with the pre-transition offset. The run then fires at 03:30 local on that day. Consequence: a report an hour late on a few days a year (C3, R1). Confidence medium: it needs a schedule in the gap.
**Fix:** Normalize nonexistent wall times to the first valid instant after the gap and say so in the docstring, or reject such times at creation.
**Cite:** PEP 495 (local time disambiguation, `fold`); Python docs, datetime ("Aware and Naive Objects")
**Source:** model · confidence: medium

### [minor] `module_c.py:137` PY-DIFF-01: Debug print on the billing request path

```python
print("DEBUG invoice", invoice)
```

**Why:** The print runs on every POST /billing/run, writes the invoice's customer and line items to stdout, bypasses the logger and has no level. Raised from nit to minor because it sits on a request path (X-SEV-07).
**Fix:** Delete it, or log at debug level through `logger.debug` without the line items.
**Cite:** CWE-532; CWE-489 (active debug code)
**Source:** ruff (T201) · confidence: high

### [minor] `test_module_e.py:61` PY-TEST-02: Assertion on the reservation list is always true

```python
assert len(response.get_json()["reservations"]) >= 0
```

**Why:** The condition can never fail. The reservation created at line 58 is never checked, so a list that drops it still passes. The status-code check on line 60 is kept.
**Fix:** Assert the count and content: `assert len(...) == 1` and that its `sku` is "BOLT-M8".
**Cite:** pytest docs, "Asserting with the assert statement"
**Source:** model · confidence: high

### [minor] `test_module_e.py:86` PY-TEST-06: Purchase-order total test skipped with no reason

```python
@pytest.mark.skip
```

**Why:** The skip has no reason or ticket. It disables the only check of the purchase-order total, which fails today (0.29 x 3 gives 86, expected 87; see module_e.py:168). The route is behind a visible role check (module_e.py:158), so the coverage loss is C2 with R2 and minor under D1 (severity reference section 2).
**Fix:** Fix the float handling and unskip, or use `@pytest.mark.xfail(reason="TICKET-n: ...", strict=True)`.
**Cite:** pytest docs, "Skip and xfail" (reason, strict)
**Source:** model · confidence: high

### [nit] 2 unused imports from ruff (F401)

Collapsed because ruff reports them. Run `ruff check --fix` on module_c.py and module_e.py.

### [nit] 1 print from ruff (T201)

module_b.py:175, the cron summary line (intended CLI output). Collapsed; kept in the JSON report.

## Questions

Low-confidence blockers or majors, and absence-of-control items, go here, not above. Questions do not change the verdict.

- `module_a.py:139` — Is this blueprint behind the admin app's before_request authentication? The docstring says it is, but no gate is visible in this file. If it is not, any caller can charge any customer by email (POST /billing/run) and download any export (GET /billing/exports).
- `module_c.py:124` — Same question as module_a.py:139, for this copy of the blueprint: is /billing/run and /billing/exports gated by the admin app? If not, the path traversal and SQL findings above are reachable by anyone.

## Pre-existing (not part of this change)

None: file scope, so nothing is pre-existing.

