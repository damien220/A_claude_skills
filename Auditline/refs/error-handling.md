# Error handling

Sources: PEP 8 ("Programming Recommendations"); PEP 3134 (exception chaining); Python docs
(`asyncio`, `logging`, `subprocess`, `assert`, `contextlib`); Node.js docs (`process`, `Error`
`cause`, `stream.pipeline`); WHATWG Fetch Standard; RFC 9110, RFC 9457; Express, Fastify, React
and TanStack Query docs; AWS Builders' Library; MITRE CWE as cited per rule.

## Contents

1. How to use this ref
2. Rule map
3. Catching: ERR-01, ERR-02, ERR-03
4. I/O boundaries and responses: ERR-04, ERR-05, ERR-10
5. Cleanup and consistency: ERR-06, ERR-07
6. Background work and assertions: ERR-08, ERR-09
7. Frontend: ERR-11
8. Do not flag

## 1. How to use this ref

- **Rule IDs.** `<LANG>-ERR-NN`; the number is the concept across languages. `PY-ERR-01` is the
  swallowed exception the P1 sample report uses.
- **Where the failure lands decides the level.** A swallowed or mishandled error on a money, auth or
  persistent-write path is one level up (U1, X-SEV-05). The same code around a cache warm-up or
  telemetry call is minor. Trace what the caller does when the error vanishes.
- **Error detail in responses is not defined here.** A response that carries `err.message`,
  `err.stack`, `traceback.format_exc()` or a raw error object is `PY-SEC-18` / `NODE-SEC-18`
  (CWE-209, `refs/security.md`). Report it there so it survives `--security-only`; do not add a
  second finding or ID. ERR-05 covers the status code and shape of error responses only.
- **Tools first.** `ruff` (`S110`, `S112`, `BLE001`, `E722`, `S113`, `PLW1510`, `SIM115`, `B904`,
  `TRY400`) and typescript-eslint (`no-floating-promises`, `no-misused-promises`) report their hits
  as tool findings. Add model findings for what they cannot judge (which errors matter, what the
  caller does).

## 2. Rule map

| ID | Defect | Languages | Default severity |
|---|---|---|---|
| ERR-01 | Swallowed exception | PY, NODE, TS | major on money/write path, else minor (X-SEV-05) |
| ERR-02 | Over-broad catch or try body | PY, NODE | minor; major if it hides bugs or cancellation |
| ERR-03 | Lost cause and stack | PY, NODE, TS | minor |
| ERR-04 | Unchecked I/O result, no timeout | PY, NODE, TS | major on main flow |
| ERR-05 | Wrong status code or error shape | PY, NODE | minor; major if the contract breaks |
| ERR-06 | Cleanup missing on the error path | PY, NODE | major if it leaks per request |
| ERR-07 | Multi-step write with no transaction | PY, NODE | major |
| ERR-08 | Background failure never observed | PY, NODE | major; blocker if anyone can crash the process |
| ERR-09 | `assert` used for runtime validation | PY | major on untrusted input |
| ERR-10 | Retry without bound, backoff or filter | PY, NODE, TS | major on shared dependency |
| ERR-11 | UI error and loading state | TS | major on main flow |

## 3. Catching

### PY-ERR-01 · NODE-ERR-01 · TS-ERR-01 — Swallowed exception
- **Detect:** X-SEV-05 settles the level and shows `except Exception: pass`. Also: `with
  contextlib.suppress(Exception):` around a write; `except Exception: return None` (or `False`,
  `[]`) where the caller treats the value as a normal result; `except …: continue` in a loop that
  processes records; `.catch(() => {})` and `.catch(() => null)`; `catch (e) { console.log(e) }`
  followed by normal flow; `Promise.allSettled(...)` whose rejected entries are never read.
- **Default severity:** per X-SEV-05: major on a money or data-write path (U1); minor for
  best-effort work (cache warm-up, telemetry, optional enrichment).
- **Why:** the failure disappears and the caller carries on as if it had worked.
- WRONG:
  ```python
  with contextlib.suppress(Exception):
      ledger.post(entry)                       # a failed post is invisible
  def charge(invoice: Invoice) -> Receipt | None:
      try:
          return gateway.charge(invoice)
      except Exception:
          return None                          # declined, timed out and bug all look the same
  ```
  ```js
  await sendReceipt(order).catch(() => {});          // fine if best-effort; a finding if it is the refund
  ```
- CORRECT:
  ```python
  try:
      ledger.post(entry)
  except LedgerError:
      logger.exception("ledger post failed for entry %s", entry.id)
      raise
  ```
  ```js
  await sendReceipt(order).catch((err) => req.log.warn({ err, orderId: order.id }, 'receipt not sent'));
  ```
- **Fix:** catch the specific error; log with context; re-raise or return an explicit failure
  type the caller must handle.
- **Cite:** CWE-390; CWE-396; CWE-391; PEP 8, "Programming Recommendations".
- **Tool code:** `[ruff: S110, S112, BLE001, E722]`, `[eslint: no-empty]`. (`SIM105` suggests
  `suppress` for a specific exception and flags the acceptable form; do not cite it.)

### PY-ERR-02 · NODE-ERR-02 — Over-broad catch or try body
- **Detect:** a `try` block of many statements whose single `except Exception` / `catch` maps to
  one outcome (for example "not found"); a bare `except:` or `except BaseException:` (also catches
  `KeyboardInterrupt`, `SystemExit` and `asyncio.CancelledError`, which breaks timeouts and task
  cancellation); a JS `catch` that returns 404 or a default for every error, including `TypeError`
  from a bug; a catch that does not re-throw errors it did not expect.
- **Default severity:** minor (C3). Major when it hides programming errors on a data-write path
  (a typo becomes "record not found"), or when it swallows `CancelledError` and leaves tasks
  uncancellable.
- **Why:** a wide net turns bugs into expected outcomes and removes the traceback.
- WRONG:
  ```python
  try:
      user = repo.get(user_id)
      plan = PLANS[user.plan_id]
      price = plan.price_for(user.region)       # KeyError, AttributeError, bugs: all become 404
  except Exception:
      abort(404)
  ```
  ```python
  try:
      await asyncio.wait_for(job(), 5)
  except BaseException:                          # swallows CancelledError
      logger.error("job failed")
  ```
  ```js
  try { return await readConfig(path); } catch { return {}; }   // EACCES and bad JSON become "empty config"
  ```
- CORRECT:
  ```python
  user = repo.get(user_id)                       # raises UserNotFound
  try:
      plan = PLANS[user.plan_id]
  except KeyError:
      abort(404)
  ```
  ```js
  try { return await readConfig(path); }
  catch (err) { if (err.code === 'ENOENT') return {}; throw err; }
  ```
- **Fix:** one risky call per `try`; catch the specific class; re-raise the rest; never catch
  `BaseException` without re-raising `CancelledError`.
- **Cite:** PEP 8, "Programming Recommendations" (limit the `try` clause; avoid bare `except`);
  Python docs, `asyncio.CancelledError` (must be re-raised in almost all situations); Node.js docs,
  "Errors"; CWE-396; CWE-755.
- **Tool code:** `[ruff: BLE001, E722]`; the try-body size and the `BaseException` case are
  model findings.

### PY-ERR-03 · NODE-ERR-03 · TS-ERR-03 — Lost cause and stack
- **Detect:** Python: `raise AppError(str(err))` or `raise AppError("failed")` inside `except`
  with no `from err`; `logger.error(f"failed: {err}")` instead of `logger.exception(...)`;
  `print(e)`. JS: `throw new Error(err.message)` (drops the type, code and stack);
  `console.error(err.message)`; `reject(err.message)`; `log.error(err.message)` where the logger
  serializes an `err` object.
- **Default severity:** minor (C3). Nit for B904 alone: Python already chains implicitly, so the
  traceback shows both errors; the explicit `from` states the intent.
- **Why:** the log line says "failed" and nothing says why; the trace to the root cause is gone.
- WRONG:
  ```python
  except requests.RequestException as err:
      logger.error(f"charge failed: {err}")                  # no traceback
      raise ChargeError("charge failed")                      # cause not stated
  ```
  ```js
  } catch (err) {
    req.log.error(err.message);
    throw new Error(err.message);                              // new stack, old type and code gone
  }
  ```
- CORRECT:
  ```python
  except requests.RequestException as err:
      logger.exception("charge failed for invoice %s", invoice.id)
      raise ChargeError("charge failed") from err
  ```
  ```js
  } catch (err) {
    req.log.error({ err, invoiceId }, 'charge failed');
    throw new Error('charge failed', { cause: err });
  }
  ```
- **Fix:** `logging.exception` / `exc_info=True`; `raise … from err`; `new Error(msg, { cause })`;
  log the error object under the logger's `err` key.
- **Cite:** PEP 3134 (exception chaining); Python docs, `logging.exception`; MDN, `Error: cause`;
  pino docs, "Pino standard serializers" (`err`); CWE-778 (insufficient logging).
- **Tool code:** `[ruff: B904, TRY400, TRY201]`, `[eslint: preserve-caught-error]` (ESLint 9.35 and
  later).

## 4. I/O boundaries and responses

### PY-ERR-04 · NODE-ERR-04 · TS-ERR-04 — Unchecked I/O result, no timeout
- **Detect:** Python: `requests.get(url)` with no `timeout` (waits forever) and no
  `raise_for_status()` (an error page is parsed as data); `subprocess.run(...)` with no
  `check=True` and no return-code test; `json.loads(external)` with no handling of `ValueError`;
  an `UPDATE`/`DELETE` whose `rowcount` of 0 is treated as success. JS/TS: `fetch` with no
  `res.ok` test (it resolves on HTTP 404 and 500) and no `AbortSignal.timeout(ms)`; `res.json()`
  on a body that may be HTML; `JSON.parse(req.body)` that throws a 500 for client input. (`axios`
  throws on non-2xx by default; do not flag it for a missing status check.)
- **Default severity:** major on a request path or main flow (C2/R1: a hung dependency holds the
  worker; an error body becomes data); minor in a one-off script.
- **Why:** an I/O call has three outcomes (success, error response, no response); the code
  handles only the first.
- WRONG:
  ```python
  rates = requests.get(RATES_URL).json()               # no timeout, no status check
  subprocess.run(["pg_dump", db_url, "-f", path])      # a failed dump goes unnoticed
  ```
  ```tsx
  const res = await fetch(`/api/products/${id}`);
  const product = await res.json();                     // a 500 page throws "Unexpected token <"
  ```
- CORRECT:
  ```python
  resp = requests.get(RATES_URL, timeout=(3.05, 10))
  resp.raise_for_status()
  rates = resp.json()
  subprocess.run(["pg_dump", db_url, "-f", path], check=True, timeout=300)
  ```
  ```tsx
  const res = await fetch(`/api/products/${id}`, { signal: AbortSignal.timeout(10_000) });
  if (!res.ok) throw new HttpError(res.status);
  const product: unknown = await res.json();
  ```
- **Fix:** a timeout on every outbound call; check the status; validate the body at the boundary;
  decide what the caller sees on each failure.
- **Cite:** WHATWG Fetch Standard (the promise rejects only on network errors); MDN, `Response.ok`
  and `AbortSignal.timeout()`; Requests docs, "Timeouts" (production code should set one); Python
  docs, `subprocess.run` (`check`); CWE-252; CWE-754; CWE-400.
- **Tool code:** `[ruff: S113, PLW1510]`, `[typescript-eslint: no-floating-promises]`.

### PY-ERR-05 · NODE-ERR-05 — Wrong status code or error shape
- **Detect:** validation, not-found, conflict or auth failures that surface as 500 (an uncaught
  exception, `throw` in a handler with no mapping); HTTP 200 with `{ "success": false }` or
  `{ "error": … }`; error bodies whose shape differs from the sibling routes (or from
  `application/problem+json`, RFC 9457); an Express error handler with three parameters instead
  of four (`(err, req, res)` is not recognised as an error handler); 401 and 403 swapped.
  Error **detail** in the body is `PY-SEC-18` / `NODE-SEC-18`, not this rule.
- **Default severity:** minor (C3). Major when the wrong code breaks a documented or public
  contract, makes clients retry a non-retryable request (a 500 for bad input), or hides failures
  from monitoring and caches (a 200 error body).
- **Why:** clients, proxies and alerting act on the status code; a wrong one changes their
  behaviour.
- WRONG:
  ```python
  @bp.post("/orders")
  def create_order() -> ResponseReturnValue:
      qty = int(request.json["qty"])                  # ValueError → 500 for a client mistake
      if qty < 1:
          return jsonify(success=False, error="bad qty"), 200
  ```
  ```js
  app.use((err, req, res) => res.status(500).send('error'));     // 3 args: Express skips it
  ```
- CORRECT:
  ```python
  if not isinstance(qty, int) or qty < 1:
      return jsonify(type="about:blank", title="Invalid quantity", status=422), 422, {
          "Content-Type": "application/problem+json"}
  ```
  ```js
  app.use((err, req, res, next) => {                              // 4 args
    req.log.error({ err }, 'request failed');
    res.status(err.status ?? 500).type('application/problem+json')
      .json({ type: 'about:blank', title: err.expose ? err.message : 'Internal Server Error', status: err.status ?? 500 });
  });
  ```
- **Fix:** validate at the boundary and return 400/422; map domain errors to 4xx in one handler;
  use one problem shape across routes.
- **Cite:** RFC 9457 (problem details); RFC 9110 §15 (4xx client errors, 5xx server errors);
  Express docs, "Error Handling" (four-argument handler); Fastify docs, "Errors" (`setErrorHandler`).
- **Tool code:** none.

### PY-ERR-10 · NODE-ERR-10 · TS-ERR-10 — Retry without bound, backoff or filter
- **Detect:** `while True: try: … except: sleep(1)` with no attempt limit; a fixed delay with no
  jitter against a shared service; retrying every error including 400, 401 and validation
  failures; a retry wrapper around a client that already retries (multiplied attempts); a retry
  around a non-idempotent POST (see `COR-02`); a loop that retries and, after the last attempt,
  falls through as if it had succeeded.
- **Default severity:** major when unbounded or without backoff against a shared dependency
  (C2/R1: a retry storm turns a brief outage into a long one); minor otherwise.
- **Why:** synchronized retries from many clients arrive together and keep the dependency down.
- WRONG:
  ```python
  while True:
      try:
          return client.fetch(key)
      except Exception:
          time.sleep(1)                          # forever, same delay, every error
  ```
  ```js
  for (let i = 0; i < 3; i++) {
    try { await send(msg); } catch { /* try again */ }
  }                                                // after 3 failures, continues as if sent
  ```
- CORRECT:
  ```python
  for attempt in range(5):
      try:
          return client.fetch(key)
      except TransientError:
          if attempt == 4:
              raise
          time.sleep(min(30, 2 ** attempt) * random.uniform(0.5, 1.0))
  ```
  ```js
  let lastErr;
  for (let i = 0; i < 3; i++) {
    try { return await send(msg); }
    catch (err) { if (!isTransient(err)) throw err; lastErr = err; await sleep(2 ** i * 100 * (0.5 + Math.random())); }
  }
  throw new Error('send failed after 3 attempts', { cause: lastErr });
  ```
- **Fix:** a maximum attempt count, exponential backoff with jitter, retry only transient
  errors, raise after the last attempt; use the library's retry policy (tenacity, p-retry) once.
- **Cite:** AWS Builders' Library, "Timeouts, retries, and backoff with jitter"; Google SRE
  Book, "Addressing Cascading Failures"; CWE-400.
- **Tool code:** `[ruff: S110, S112]` for the silent variants; none for the policy.

## 5. Cleanup and consistency

### PY-ERR-06 · NODE-ERR-06 — Cleanup missing on the error path
- **Detect:** Python: `f = open(...)` with no `with`; `conn = connect(); …; conn.close()` where an
  exception skips the `close`; `lock.acquire()` with no `with` or `finally`; a SQLAlchemy session
  not used as a context manager and never rolled back; temp files not removed. Node:
  `const client = await pool.connect(); await client.query(…); client.release();` (the release is
  skipped when the query throws, so the pool drains); a read stream not destroyed on error
  (`.pipe()` instead of `pipeline`); `setInterval` or a listener never cleared; a transaction with
  `BEGIN` and no `ROLLBACK` in the catch.
- **Default severity:** major when each failed request leaks a connection, handle or lock on a
  request path (C2/R1: after a few failures the service stops answering); minor in scripts.
- **Why:** the leak happens only on failure, so tests pass and production degrades slowly.
- WRONG:
  ```python
  f = open(path)
  rows = parse(f.read())            # parse raises → f is closed only when garbage-collected
  f.close()
  ```
  ```js
  const client = await pool.connect();
  const { rows } = await client.query('SELECT … WHERE id = $1', [id]);   // throws → never released
  client.release();
  ```
- CORRECT:
  ```python
  with open(path) as f:
      rows = parse(f.read())
  ```
  ```js
  const client = await pool.connect();
  try {
    const { rows } = await client.query('SELECT … WHERE id = $1', [id]);
    return rows;
  } finally {
    client.release();
  }
  ```
- **Fix:** `with` / `try … finally`; `pipeline()` for streams; `contextlib.closing` for objects
  without a context manager; roll back in the error path.
- **Cite:** Python docs, "The with statement" and `contextlib`; node-postgres docs, "Pooling" (a
  checked-out client must be released); Node.js docs, `stream.pipeline`; CWE-772; CWE-404.
- **Tool code:** `[ruff: SIM115]`; none for Node.

### PY-ERR-07 · NODE-ERR-07 — Multi-step write with no transaction
- **Detect:** two or more dependent writes in separate statements or commits (create order, then
  decrement stock, then record payment) with no surrounding transaction; an external side effect
  (charge, email, queue publish) between two database writes with no record of the attempt;
  "dual write" to the database and a message broker; a failure handler that logs and moves on,
  leaving the first write in place.
- **Default severity:** major (C1 data or money inconsistent / R2 on the failure window). Do not
  raise to blocker unless the diff shows the failure is the common path.
- **Why:** a failure between the steps leaves a state no code path expects: a charge with no
  ledger row, an order with no stock change.
- WRONG:
  ```python
  order = Order(**data); db.session.add(order); db.session.commit()
  gateway.charge(order)                       # fails → order exists, unpaid, no record of the attempt
  inventory.decrement(order.sku, order.qty); db.session.commit()
  ```
- CORRECT:
  ```python
  with db.session.begin():
      order = Order(**data, status="pending"); db.session.add(order)
      inventory.reserve(order.sku, order.qty)
  charge = gateway.charge(order, idempotency_key=f"order-{order.id}")
  with db.session.begin():
      order.status = "paid"; order.charge_id = charge.id
  ```
  ```js
  await db.tx(async (t) => {                                   // pg-promise: one transaction; the event is an outbox row
    await t.none('INSERT INTO orders …', [order]);
    await t.none('INSERT INTO outbox (topic, payload) VALUES ($1, $2)', ['order.created', order]);
  });
  ```
- **Fix:** one transaction for the writes; record intent before the external call and the result
  after; an outbox for events; make the sequence resumable and idempotent.
- **Cite:** PostgreSQL docs, "Transactions"; SQLAlchemy docs, "Session Basics" (transactions);
  microservices.io, "Transactional outbox"; CWE-755.
- **Tool code:** none.

## 6. Background work and assertions

### PY-ERR-08 · NODE-ERR-08 — Background failure never observed
- **Detect:** Python: `asyncio.create_task(coro())` with no done callback or later `await` (the
  exception surfaces only as "Task exception was never retrieved" at garbage collection);
  `executor.submit(fn)` with no `.result()` or callback; `asyncio.gather(…, return_exceptions=True)`
  whose results are never inspected; `threading.Thread(target=…)` that can raise. Node:
  `setTimeout(async () => { … })`, `emitter.on('event', async () => { throw … })` (an unhandled
  rejection: since Node 15 the default mode is `throw`, which ends the process); an Express 4
  `async` route handler with no wrapper (the rejection is unhandled and the request hangs; Express
  5 forwards it to the error handler).
- **Default severity:** major (C2/R1: work silently fails, or the process dies). Blocker when any
  anonymous request can trigger the rejection that crashes the process (C1/R1).
- **Why:** nothing is waiting for the result, so the error has nowhere to go.
- WRONG:
  ```python
  asyncio.create_task(sync_to_crm(order))                  # failure is invisible
  ```
  ```js
  app.get('/report/:id', async (req, res) => {              // Express 4: a throw here is unhandled
    res.json(await buildReport(req.params.id));
  });
  queue.on('job', async (job) => { await handle(job); });    // a bad job crashes the process
  ```
- CORRECT:
  ```python
  def _done(task: asyncio.Task[None]) -> None:
      tasks.discard(task)
      if not task.cancelled() and (exc := task.exception()) is not None:
          logger.error("crm sync failed", exc_info=exc)

  task = asyncio.create_task(sync_to_crm(order))
  tasks.add(task)                                           # keeps a reference
  task.add_done_callback(_done)
  ```
  ```js
  app.get('/report/:id', wrap(async (req, res) => { res.json(await buildReport(req.params.id)); }));
  queue.on('job', (job) => { handle(job).catch((err) => log.error({ err, jobId: job.id }, 'job failed')); });
  ```
- **Fix:** keep the task reference and log failures in a done callback; wrap async handlers (or use
  Express 5 / Fastify, which handle them); attach `.catch` at every event-emitter boundary.
- **Cite:** Python docs, `asyncio.create_task` and "Developing with asyncio" (task exceptions
  never retrieved); Node.js docs, `process` "unhandledRejection" (default `throw` since v15);
  Express docs, "Error Handling" (promise rejections in Express 5); CWE-248; CWE-755.
- **Tool code:** `[ruff: RUF006]`, `[typescript-eslint: no-misused-promises, no-floating-promises]`.

### PY-ERR-09 — `assert` used for runtime validation
- **Detect:** `assert isinstance(payload, dict)`, `assert amount > 0`, `assert user.is_admin`,
  `assert token_valid(t)` on data from a request, file or third party. The statement is removed
  when Python runs with `-O` or `PYTHONOPTIMIZE`, and otherwise it fails as `AssertionError`
  (a 500).
- **Default severity:** major when it guards untrusted input or a business rule (C2/R1); when it
  guards an authorization decision, it is a security finding (blocker, X-SEV-04). Minor for
  documented internal invariants.
- **Why:** assertions state what the programmer believes, not what the data is; with `-O` the
  check is gone.
- WRONG:
  ```python
  def refund(order_id: int, amount: Decimal) -> None:
      assert amount > 0, "amount must be positive"          # removed under python -O
      assert current_user.is_admin
  ```
- CORRECT:
  ```python
  def refund(order_id: int, amount: Decimal) -> None:
      if amount <= 0:
          raise ValueError("amount must be positive")
      if not current_user.is_admin:
          raise PermissionDenied
  ```
- **Fix:** raise a real exception; keep `assert` for invariants and tests.
- **Cite:** Python docs, "The assert statement" (removed when optimization is requested);
  Bandit B101; CWE-617; CWE-754.
- **Tool code:** `[ruff: S101]` (noisy in tests: ignore test files).

## 7. Frontend

### TS-ERR-11 — UI error and loading state
- **Detect:** `setLoading(true); await load(); setLoading(false);` with no `try … finally` (a
  throw leaves the spinner on forever: the corpus case); a query whose `error` / `isError` is never
  read, with `data.items.map(…)` below it; an async `onSubmit` or `onClick` with no `catch`, so the
  user sees nothing and the console shows an unhandled rejection; no error boundary around a
  subtree that can throw while rendering; a Next.js route segment with a data fetch and no
  `error.tsx`. (An error boundary does not catch errors in event handlers or async code.)
- **Default severity:** major on a main flow (the user is stuck or never learns the save failed,
  C2/R1); minor on a secondary widget.
- **One finding per defect.** When the same function also has no `res.ok` check (`TS-ERR-04`),
  report one finding, `TS-ERR-11`, anchored on the unguarded call, and name the status check in
  `fix`. Use `TS-ERR-04` alone when the UI state is handled and only the check is missing.
- **Why:** the failure path is part of the screen; without it the UI shows a spinner or a blank.
- WRONG:
  ```tsx
  async function load() {
    setLoading(true);
    const res = await fetch(`/api/orders/${id}`);
    setOrder(await res.json());
    setLoading(false);                       // never runs when fetch or json throws
  }
  ```
- CORRECT:
  ```tsx
  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/orders/${id}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setOrder(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }
  // render: if (error) return <p role="alert">{error}</p>;
  ```
- **Fix:** `try / catch / finally`; render an error state; use the query library's `isError`;
  add error boundaries and `error.tsx` for render and route failures.
- **Cite:** React docs, "Catching rendering errors with an error boundary" (boundaries do not
  catch event-handler or async errors); TanStack Query docs, "Queries" (`isError`, `error`);
  Next.js docs, "Error Handling" (`error.js`); WCAG 2.2 SC 4.1.3 Status Messages (use
  `role="alert"`); CWE-755.
- **Tool code:** `[typescript-eslint: no-floating-promises, no-misused-promises]`.

## 8. Do not flag

| Pattern | Why it is not a finding |
|---|---|
| `except Exception` at a top-level boundary (request handler, worker loop) that logs with a traceback and returns a generic error | that is the boundary's job |
| `except KeyError: pass` or `contextlib.suppress(FileNotFoundError)` around an optional file | specific, expected, and harmless |
| `.catch(() => {})` on telemetry, prefetch or a best-effort cache write | best-effort work (X-SEV-05 minor at most) |
| A shutdown handler without its own `try/catch` | a rejection ends the process, which is its goal (noise table) |
| `assert` in tests, or documenting an internal invariant | not a runtime check on untrusted data |
| Missing `res.ok` check when the wrapper (axios, a typed client) throws on non-2xx | it is checked |
| A missing retry | not a defect without a failing scenario in this code |
| Error detail in a response body | `PY-SEC-18` / `NODE-SEC-18`, reported once there |
