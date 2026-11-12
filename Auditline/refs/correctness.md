# Correctness

Sources: Python docs (Tutorial, Programming FAQ, `datetime`, `decimal`, `re`, `asyncio`,
`functools`); ECMA-262 and MDN (`Array`, `Date`, `RegExp`, `Object.assign`, `Number`); React
docs; TanStack Query docs; PostgreSQL, Django and SQLAlchemy docs; MITRE CWE; IETF
`draft-ietf-httpapi-idempotency-key-header`; RFC 9111 as cited per rule.

## Contents

1. How to use this ref
2. Rule map
3. Shared state and aliasing: COR-01, COR-03, COR-16
4. Absent and falsy values: COR-04, COR-05
5. Boundaries, time and numbers: COR-06, COR-07, COR-08
6. Concurrency and async: COR-02, COR-09, COR-10
7. React state and effects: COR-11, COR-12, COR-13
8. Comparisons and validation: COR-14, COR-15
9. Do not flag

## 1. How to use this ref

- **Rule IDs.** `<LANG>-COR-NN`. The number is the concept: `PY-COR-09` and `NODE-COR-09` are the
  same defect. A language without the concept skips the number. `PY-COR-01` and `PY-COR-02` are
  the IDs the P1 sample report already uses (mutable default; charge without idempotency key).
- **Rate the outcome, not the pattern.** Follow the value to where it lands (billed, persisted,
  returned to another user, used in an auth decision) and apply `refs/severity-and-output-format.md`
  §1. "Mutable default" is a blocker when it reaches a bill and a latent minor when nothing
  mutates it. Write the failing input in `why` ("page = 3, total = 40, size = 20 drops row 41").
- **A correctness claim needs a failing input.** If you cannot name a value that gives the wrong
  result, it is a question or silence.
- **Tools own what they report.** mypy (`union-attr`, `unused-coroutine`), tsc (`strict`,
  `noUncheckedIndexedAccess`), `react-hooks/exhaustive-deps` and ruff `B006`/`DTZ*` report their
  hits as `source: ruff|mypy|eslint|tsc`. Add a model finding only for what the tool cannot see
  (the rule text says which).
- **Security overlap.** When the wrong result is an access decision, serves one user's data to
  another, or reaches a sink, file it under the `-SEC-` rule (`refs/security.md`: `-SEC-04` for
  cross-user data and bypassed checks) and do not add a second finding. That is also what keeps it
  in a `--security-only` review.

## 2. Rule map

| ID | Defect | Languages | Default severity |
|---|---|---|---|
| COR-01 | Shared mutable state across calls | PY, NODE | by X-SEV-01 |
| COR-02 | Duplicable external effect without an idempotency key | PY, NODE, TS | major |
| COR-03 | In-place mutation and aliasing of caller-owned data | PY, NODE, TS | major |
| COR-04 | Absent value dereferenced | PY, NODE, TS | major |
| COR-05 | Falsy value treated as missing | PY, NODE, TS | major on money/limits, else minor |
| COR-06 | Boundary and pagination off-by-one | PY, NODE, TS | major |
| COR-07 | Time zones and date arithmetic | PY, NODE, TS | major on stored/billed/expiry; minor when the wrong value needs an edge date or a trusted caller |
| COR-08 | Floating point money | PY, NODE, TS | blocker if charged or stored and any caller can trigger it; major behind a role check |
| COR-09 | Read-modify-write race | PY, NODE | major; blocker on balance/stock only when ordinary concurrent traffic hits it (R1) |
| COR-10 | Async work not awaited | PY, NODE, TS | major if the caller assumes the work is done, else minor; auth → SEC-20 |
| COR-11 | Stale closure and effect dependencies | TS | major if visible data goes wrong, minor if cosmetic or self-correcting |
| COR-12 | Out-of-order responses and effect cleanup | TS | major |
| COR-13 | Redundant state and wrong list keys | TS | minor; major if wrong row |
| COR-14 | Comparison semantics | PY, NODE, TS | minor |
| COR-15 | Unanchored or stateful regex | PY, NODE | by what it guards |
| COR-16 | Cache key missing a dimension | PY, NODE, TS | blocker cross-user, else major |

**Table defaults are starting points.** The "Default severity" column names the usual level for the
pattern; the C x R trace in `refs/severity-and-output-format.md` §1 decides the finding. A trace
that lowers a default is correct, and the finding says why. How to trace the two that most often
go wrong: a **race** (COR-09) is R1 only when two ordinary requests overlap without any special
timing (a public endpoint on a hot row); when it needs an unlikely interleaving or one worker, it
is R2 and the level is major (or a question). A **float total** (COR-08) is a blocker when the
value is charged or stored and any user reaches it (R1); behind a role check that only trusted
staff pass (R2) it is major. A date or expiry slip (COR-07) that needs an edge date to fail, and
an un-awaited call (COR-10) or a stale closure (COR-11) whose effect is cosmetic or self-correcting,
are minor.

## 3. Shared state and aliasing

### PY-COR-01 · NODE-COR-01 — Shared mutable state across calls
- **Detect:** severity and the basic mutable-default pattern are settled in X-SEV-01. Look also
  for: a value returned by `@lru_cache` / `@cache` that the caller mutates (the cache hands out
  the same object every time); `Object.assign(DEFAULTS, overrides)` (mutates its first argument);
  a module-level `let`/`dict` holding per-request data (`let currentUser`) that a hook sets and a
  handler reads while other requests interleave at every `await`; class attributes initialised
  to `[]` or `{}`.
- **Default severity:** per X-SEV-01: blocker when it leaks across requests, users or runs
  (module-level `currentUser` returns another user's data); major inside one run; minor when it
  is never mutated.
- **Why:** one object is created once and every call, request or client sees the same one.
- WRONG:
  ```python
  @lru_cache(maxsize=None)
  def tax_rules(region: str) -> list[Rule]:
      return load_rules(region)

  def rules_for(order: Order) -> list[Rule]:
      rules = tax_rules(order.region)
      rules.append(order_rule(order))          # mutates the cached list for every later caller
      return rules
  ```
  ```js
  const DEFAULTS = { retries: 3, headers: {} };
  export function makeClient(opts = {}) {
    return new Client(Object.assign(DEFAULTS, opts));   // the next client inherits this one's options
  }
  let currentUser;                                       // module scope: shared by all requests
  app.addHook('preHandler', async (req) => { currentUser = await loadUser(req); });
  app.get('/me', async () => currentUser);
  ```
- CORRECT:
  ```python
  def rules_for(order: Order) -> list[Rule]:
      return [*tax_rules(order.region), order_rule(order)]   # new list; or return a tuple
  ```
  ```js
  export function makeClient(opts = {}) {
    return new Client({ ...DEFAULTS, ...opts, headers: { ...DEFAULTS.headers, ...opts.headers } });
  }
  app.addHook('preHandler', async (req) => { req.user = await loadUser(req); });
  app.get('/me', async (req) => req.user);
  ```
- **Fix:** copy before mutating; keep per-request data on the request object or in
  `AsyncLocalStorage`; return tuples or frozen objects from caches.
- **Cite:** Python Programming FAQ, "Why are default values shared between objects?"; Python
  docs, `functools.lru_cache`; MDN, `Object.assign` (modifies and returns the target); Node.js
  docs, `AsyncLocalStorage`; CWE-488 (exposure of data to the wrong session).
- **Tool code:** `[ruff: B006, RUF012]` (defaults and class attributes only; cached-return
  mutation and module-level request state are model findings).

### PY-COR-03 · NODE-COR-03 · TS-COR-03 — In-place mutation and aliasing of caller-owned data
- **Detect:** Python: `items.sort()` / `.reverse()` / `.append()` / `.update()` on a parameter
  the caller keeps using; `x = items.sort()` (returns `None`); `[[0] * n] * m` (every row is one
  list); `b = a` then `b.append`; shallow `.copy()` / `[:]` / `dict(d)` of nested data followed
  by a nested mutation; removing from a list inside `for x in items`. JS/TS: `props.items.sort()`,
  `.reverse()`, `.splice()` on props, state or a function argument; `Array(n).fill([])` (one
  shared inner array); `{...obj}` followed by `copy.nested.x = 1`; React state mutated and set
  back: `state.items.push(x); setState(state)` (same reference, no re-render);
  `arr.forEach(x => arr.splice(...))`.
- **Default severity:** major (C2/R1: the caller's list is reordered or the UI does not update).
  Blocker when the mutated data is money, permissions or stored state read by other users (C1).
  Minor when the mutation is invisible to every caller (a local copy that is never reused).
- **Why:** the caller and callee hold one object. Removing while iterating skips the next element:
  `for n in xs: if n % 2 == 0: xs.remove(n)` on `xs = [2, 4, 6, 7]` leaves `[4, 7]`.
- WRONG:
  ```python
  def top_three(scores: list[int]) -> list[int]:
      scores.sort(reverse=True)               # reorders the caller's list
      return scores[:3]
  grid = [[0] * 3] * 3                         # grid[0][0] = 1 changes all three rows
  ```
  ```tsx
  const sorted = props.items.sort((a, b) => a.price - b.price);   // mutates props
  function add(item: Item) { state.items.push(item); setState(state); }   // no re-render
  ```
- CORRECT:
  ```python
  def top_three(scores: list[int]) -> list[int]:
      return sorted(scores, reverse=True)[:3]
  grid = [[0] * 3 for _ in range(3)]
  ```
  ```tsx
  const sorted = props.items.toSorted((a, b) => a.price - b.price);   // or [...props.items].sort(...)
  function add(item: Item) { setState({ ...state, items: [...state.items, item] }); }
  ```
- **Fix:** `sorted()` / `toSorted()` / spread / `structuredClone` for nested data; build rows with a
  comprehension; filter into a new list instead of removing while iterating.
- **Cite:** Python docs, `list.sort` (sorts in place, returns `None`); Python Programming FAQ,
  "How do I create a multidimensional list?"; React docs, "Updating Objects in State" and
  "Updating Arrays in State"; MDN, `Array.prototype.toSorted`; CWE-1321 only for
  prototype-pollution cases, which belong to `refs/security.md`.
- **Tool code:** `[eslint: no-param-reassign (props: true)]`, `[eslint: react/no-direct-mutation-state]`
  (class components only); none for Python.

### PY-COR-16 · NODE-COR-16 · TS-COR-16 — Cache key missing a dimension
- **Detect:** a cache, memo or query key built from fewer inputs than the cached function reads:
  `@lru_cache` / `Map` keyed by `report_id` while the result also depends on the user, tenant,
  locale, feature flag or filter; Flask-Caching `@cache.cached(timeout=60)` on a per-user view
  (the default key is the path only); `Cache-Control: public` on an authenticated response with
  no `Vary`; TanStack Query `queryKey: ['todos']` whose `queryFn` reads `filter`, `page` or
  `userId`; a write path that changes the data and never invalidates the key.
- **Default severity:** blocker when another user's or tenant's data can be served (C1/R1, also
  A01); major when the wrong filter, page or locale is served (C2/R1).
- **Why:** the first caller's result is returned to everyone whose key collides.
- WRONG:
  ```python
  @cache.cached(timeout=300)                  # key = request path only
  @bp.get("/dashboard")
  @login_required
  def dashboard() -> ResponseReturnValue:
      return render_template("dashboard.html", rows=rows_for(current_user.id))
  ```
  ```tsx
  const { data } = useQuery({ queryKey: ['orders'], queryFn: () => fetchOrders(status, page) });
  ```
- CORRECT:
  ```python
  @cache.cached(timeout=300, make_cache_key=lambda: f"dashboard:{current_user.id}")
  ```
  ```tsx
  const { data } = useQuery({ queryKey: ['orders', status, page], queryFn: () => fetchOrders(status, page) });
  ```
- **Fix:** include every input in the key; do not cache per-user responses in shared caches;
  `Cache-Control: private` plus `Vary` for HTTP; call `invalidateQueries` after mutations.
- **Cite:** TanStack Query docs, "Query Keys"; RFC 9111 §4.1 (`Vary`) and §5.2.2.7 (`private`);
  Flask-Caching docs, `make_cache_key`; CWE-524 (cache containing sensitive information).
- **Tool code:** `[eslint: @tanstack/query/exhaustive-deps]` for TS query keys.

## 4. Absent and falsy values

### PY-COR-04 · NODE-COR-04 · TS-COR-04 — Absent value dereferenced
- **Detect:** Python: `re.match(...).group(1)`, `d.get(k).attr`, `session.get(Model, id).name`,
  `query.first().id`, `os.environ.get("URL") + "/x"`, `next(iter(xs))` on a possibly empty
  iterable. JS/TS: `items.find(...).id`, `map.get(k).x`, `str.match(re)[1]`, `arr[0].name`,
  `process.env.BASE_URL` passed where a string is required, `JSON.parse(body).user.id` on
  unvalidated input, non-null `!` used to silence the compiler.
- **Default severity:** major when ordinary input reaches the absent case (a not-found id turns
  into a 500 or a crash, C2/R1); minor when an invariant outside the diff makes it impossible and
  you can name it; no finding when mypy or tsc strict already reports it.
- **Why:** "not found" is a normal outcome of a lookup, and the dereference turns it into
  `AttributeError` or `TypeError`.
- WRONG:
  ```python
  order = db.session.get(Order, order_id)
  return jsonify(order.to_dict())             # order is None for an unknown id
  ```
  ```ts
  const plan = plans.find((p) => p.id === req.body.planId);
  await subscribe(user, plan.priceId);        // TypeError when planId is unknown
  ```
- CORRECT:
  ```python
  order = db.session.get(Order, order_id)
  if order is None:
      abort(404)
  return jsonify(order.to_dict())
  ```
  ```ts
  const plan = plans.find((p) => p.id === req.body.planId);
  if (!plan) return reply.code(404).send({ type: 'about:blank', title: 'Unknown plan', status: 404 });
  await subscribe(user, plan.priceId);
  ```
- **Fix:** check and return 404/422, or `next(it, default)`; enable `noUncheckedIndexedAccess`;
  replace `!` with a real check.
- **Cite:** Python docs, `re.match` (returns `None` when no match); MDN, `Array.prototype.find`
  (returns `undefined`); TypeScript handbook, "Narrowing"; CWE-476.
- **Tool code:** `[mypy: union-attr, index]`, `[tsc: TS2532, TS18048]`,
  `[typescript-eslint: no-non-null-assertion, no-unnecessary-condition]`.

### PY-COR-05 · NODE-COR-05 · TS-COR-05 — Falsy value treated as missing
- **Detect:** `x = x or default`, `if not qty:`, `limit = req.query.limit || 20`,
  `discount || 0.1`, `timeout = timeout || 30`, `if (!page)` where `0`, `''` or `False` is a legal
  value. Environment flags: `if os.environ.get("DEBUG")` and `if (process.env.FEATURE_X)` are true
  for the string `"0"` and `"false"`.
- **Default severity:** major when the clobbered value is a price, discount, quantity, limit or
  permission (a deliberate `0` becomes the default, C2/R1); minor for display values.
- **Why:** `or` / `||` test truthiness, not presence. A zero discount silently becomes the default
  discount.
- WRONG:
  ```python
  def price(base: Decimal, discount: Decimal | None = None) -> Decimal:
      discount = discount or Decimal("0.10")      # an explicit 0 becomes 10 %
      return base * (1 - discount)
  ```
  ```js
  const limit = Number(req.query.limit) || 20;     // limit=0 is replaced
  if (process.env.ENABLE_BILLING) startBilling();  // "false" is a non-empty string
  ```
- CORRECT:
  ```python
  discount = Decimal("0.10") if discount is None else discount
  ```
  ```js
  const limit = req.query.limit === undefined ? 20 : Number(req.query.limit);
  if (process.env.ENABLE_BILLING === 'true') startBilling();
  ```
- **Fix:** compare to `None` / `undefined`; use `??`; parse flags explicitly.
- **Cite:** Python docs, "Truth Value Testing"; MDN, "Nullish coalescing operator (??)" and
  "Logical OR (||)"; CWE-754 (improper check for unusual or exceptional conditions).
- **Tool code:** `[typescript-eslint: prefer-nullish-coalescing]`; none for Python.

## 5. Boundaries, time and numbers

### PY-COR-06 · NODE-COR-06 · TS-COR-06 — Boundary and pagination off-by-one
- **Detect:** `range(len(xs) - 1)`, `for (let i = 0; i <= xs.length; i++)`, slice ends mixed
  between inclusive and exclusive, `offset = page * size` with a 1-based `page`,
  `pages = total // size` (drops the partial last page), `has_next = len(rows) == size` (one empty
  trailing page), batch loops `range(0, n // size)`, day ranges written as
  `BETWEEN start AND end_of_day` or `<= '23:59:59'` (misses `23:59:59.5`), `xs[len(xs)]`, `xs[-1]`
  on an empty list.
- **Default severity:** major (C2/R1: the last record is dropped or repeated); blocker when the
  dropped or repeated record is a payment, deletion or export that others rely on (C1).
- **Why:** it works for the author's test data and fails at 0, 1, an exact multiple of the page
  size, or the last element. Name the failing size in `why`.
- WRONG:
  ```python
  pages = total // size                         # 41 rows, size 20 → 2 pages, row 41 is unreachable
  rows = query.offset(page * size).limit(size)   # page starts at 1 → the first page is skipped
  ```
  ```js
  for (let i = 0; i <= items.length; i++) total += items[i].price;   // items[length] is undefined
  ```
- CORRECT:
  ```python
  pages = -(-total // size)                      # ceiling; or math.ceil(total / size)
  rows = query.offset((page - 1) * size).limit(size)
  ```
  ```js
  for (const item of items) total += item.price;
  ```
  ```sql
  WHERE created_at >= $1 AND created_at < $2    -- half-open: start of day, start of next day
  ```
- **Fix:** iterate over elements, not indexes; half-open ranges; fetch `size + 1` rows to detect a
  next page.
- **Cite:** CWE-193 (off-by-one error); Python docs, "Common Sequence Operations" (slicing);
  Dijkstra, "Why numbering should start at zero" (EWD831) for half-open ranges.
- **Tool code:** none (model finding).

### PY-COR-07 · NODE-COR-07 · TS-COR-07 — Time zones and date arithmetic
- **Detect:** Python: `datetime.now()` / `datetime.utcnow()` (naive; `utcnow` is deprecated since
  3.12) for stored, compared or exchanged timestamps; comparing naive with aware values (raises
  `TypeError`); `date.today()` for a user's "today"; `timedelta(days=1)` added to a local wall-clock
  value across a DST change; `time.time()` for elapsed time (the clock can jump; use
  `time.monotonic()`); `replace(day=31)`; "30 days" used as "a month". JS/TS:
  `new Date('2024-03-10')` (date-only strings parse as **UTC**, date-time strings without offset
  parse as **local**); `getMonth()` is zero-based; `setMonth(+1)` from Jan 31 lands on Mar 2;
  `toISOString().slice(0, 10)` as the user's local date; `+ 24 * 3600 * 1000` for "tomorrow";
  `Date.now()` differences for durations that must survive a clock change.
- **Default severity:** major when the value is stored, billed, compared for expiry or used for a
  day boundary (C2/R1); blocker when it decides token or subscription expiry for money or access;
  minor when it is display-only.
- **Why:** the code is correct only in the author's time zone and on days without a DST change or
  a month end.
- WRONG:
  ```python
  expires_at = datetime.now() + timedelta(days=30)         # naive local time stored for a UTC reader
  if token.expires_at < datetime.now(timezone.utc): ...    # TypeError: naive vs aware
  ```
  ```js
  const start = new Date('2024-03-10');                    // UTC midnight: Mar 9 in New York
  const label = start.toISOString().slice(0, 10);          // the UTC date, not the user's local date
  next.setMonth(next.getMonth() + 1);                      // Jan 31 → Mar 2
  ```
- CORRECT:
  ```python
  expires_at = datetime.now(timezone.utc) + timedelta(days=30)
  local_midnight = datetime.combine(day, time.min, tzinfo=ZoneInfo(user.tz))
  ```
  ```js
  const start = new Date(Date.UTC(2024, 2, 10));           // explicit; or Temporal / date-fns-tz
  ```
- **Fix:** store and compare aware UTC instants; convert to the user's zone only for display
  (`zoneinfo`, `Intl.DateTimeFormat`); add calendar units with a library; `monotonic()` for
  durations.
- **Cite:** Python docs, `datetime` ("Aware and Naive Objects") and "What's New in Python 3.12"
  (`utcnow` deprecation); PEP 615 (`zoneinfo`); ECMA-262, "Date Time String Format"; MDN,
  `Date.parse`; CWE-682.
- **Tool code:** `[ruff: DTZ001, DTZ003, DTZ005, DTZ011]`; none for JS.

### PY-COR-08 · NODE-COR-08 · TS-COR-08 — Floating point money
- **Detect:** `float(...)` or `parseFloat(...)` of an amount; `price * qty * 1.2` on floats;
  `round(x, 2)` on a float (`round(2.675, 2)` is `2.67`); `Decimal(0.1)` (builds from the binary
  float: `0.1000000000000000055…`); `int(amount * 100)` (`int(19.99 * 100)` is `1998`);
  `(1.005).toFixed(2)` is `"1.00"`; `Math.round(x * 100) / 100`; a `number` / `float` column for
  currency; summing floats in a loop.
- **Default severity:** blocker when the float result is charged, stored in a ledger or compared in
  reconciliation (C1/R1: off by a cent on ordinary amounts); major when it is a displayed total.
- **Why:** binary floats cannot represent most decimal fractions, and the error shows up in cents.
- WRONG:
  ```python
  amount_cents = int(order.total * 100)          # total = 19.99 → 1998
  tax = round(subtotal * 0.0825, 2)
  ```
  ```js
  const total = items.reduce((sum, i) => sum + i.price * i.qty, 0);    // 0.1 + 0.2 = 0.30000000000000004
  await stripe.charges.create({ amount: total, currency: 'usd' });     // amount must be an integer of cents
  ```
- CORRECT:
  ```python
  amount_cents = int((Decimal(str(order.total)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
  ```
  ```js
  const totalCents = items.reduce((sum, i) => sum + i.priceCents * i.qty, 0);   // integers throughout
  ```
- **Fix:** integer minor units end to end, or `Decimal` built from strings with an explicit
  quantize and rounding mode; a decimal column in the database.
- **Cite:** Python docs, "Floating Point Arithmetic: Issues and Limitations" and `decimal`;
  ECMA-262, Number type (IEEE 754 binary64); Stripe API docs, "Currencies" (amounts in the smallest
  unit); CWE-682; CWE-1339.
- **Tool code:** none.

## 6. Concurrency and async

### PY-COR-02 · NODE-COR-02 · TS-COR-02 — Duplicable external effect without an idempotency key
- **Detect:** a POST that charges, sends mail or SMS, creates an order or publishes a message,
  placed where it can run twice: inside a retry loop or a client with automatic retries (`requests`
  `Retry` with POST in `allowed_methods`, axios-retry, a `fetch` wrapper); after a timeout that
  returns "failed" while the provider may have succeeded; in a webhook, queue or cron handler
  that is redelivered, with no stored event id or unique constraint; a submit button that is not
  disabled while the mutation is pending.
- **Default severity:** major (C2/R1: a timed-out success is charged or sent again). Blocker when
  the diff itself adds an automatic retry around a payment call that has no key (C1: a double
  charge on a common failure, the timeout).
- **Why:** a timeout does not tell you the request failed. A retry turns an unknown outcome into a
  second effect.
- WRONG:
  ```python
  response = requests.post(CHARGE_URL, json=payload, timeout=10)    # on timeout the caller retries the run
  ```
  ```js
  app.post('/webhooks/stripe', async (req) => {
    await fulfilOrder(req.body.data.object.id);       // redelivered events fulfil the order twice
  });
  ```
- CORRECT:
  ```python
  response = requests.post(CHARGE_URL, json=payload, timeout=10,
                           headers={"Idempotency-Key": f"invoice-{invoice.id}"})
  ```
  ```js
  const done = await db.query(
    'INSERT INTO processed_events (id) VALUES ($1) ON CONFLICT DO NOTHING RETURNING id', [event.id]);
  if (done.rowCount === 0) return { received: true };    // already handled
  await fulfilOrder(event.data.object.id);
  ```
- **Fix:** an `Idempotency-Key` derived from the business object (not random per attempt);
  record the attempt before calling; a unique constraint or processed-events table; disable the
  button while pending.
- **Cite:** CWE-837; IETF `draft-ietf-httpapi-idempotency-key-header`; RFC 9110 §9.2.2
  (idempotent methods; POST is not); Stripe API docs, "Idempotent requests".
- **Tool code:** none.

### PY-COR-09 · NODE-COR-09 — Read-modify-write race
- **Detect:** a value is read, a new value is computed in the application, then written, with
  no lock, transaction or atomic statement between: `acct = get(id); acct.balance -= x; save(acct)`;
  `if not exists(email): insert(...)` with no unique index; `n = await redis.get(k); await redis.set(k, n + 1)`;
  `if stock > 0: stock -= 1`. Node: `total += await fetchPart(id)` inside `Promise.all(ids.map(...))`
  (the left side is read **before** the await, so only the last write survives: three parts of 1, 2
  and 3 give `3`, not `6`). Python threads: `counter += 1` is not atomic.
- **Default severity:** major (C2: wrong result under concurrency); blocker on a balance, stock
  count or one-time token that many users can hit at once (C1/R1: double spend, oversell). If the
  path has a single writer (one cron job, one worker), make it a question.
- **Why:** two requests read the same old value and both write; one update is lost.
- WRONG:
  ```python
  acct = db.session.get(Account, account_id)
  if acct.balance < amount:
      raise InsufficientFunds
  acct.balance -= amount                    # two concurrent withdrawals both pass the check
  db.session.commit()
  ```
  ```js
  let total = 0;
  await Promise.all(ids.map(async (id) => { total += await fetchPart(id); }));   // lost updates
  ```
- CORRECT:
  ```python
  updated = db.session.execute(
      update(Account).where(Account.id == account_id, Account.balance >= amount)
      .values(balance=Account.balance - amount)
  ).rowcount
  if updated == 0:
      raise InsufficientFunds
  ```
  ```js
  const parts = await Promise.all(ids.map((id) => fetchPart(id)));
  const total = parts.reduce((a, b) => a + b, 0);
  ```
- **Fix:** one atomic `UPDATE … SET x = x - $1 WHERE x >= $1`, `SELECT … FOR UPDATE`, a unique
  constraint with an upsert, Redis `INCR`; collect results then combine; a lock only as a last
  resort.
- **Cite:** CWE-362; CWE-367; PostgreSQL docs, "Explicit Locking" and "Transaction Isolation"
  (Read Committed); Django docs, "Avoiding race conditions using `F()`"; SQLAlchemy docs,
  `with_for_update`.
- **Tool code:** `[eslint: require-atomic-updates]` (fires on the JS pattern; the SQL pattern is a
  model finding).

### PY-COR-10 · NODE-COR-10 · TS-COR-10 — Async work not awaited
- **Detect:** Python: a coroutine function called without `await` ("coroutine was never awaited":
  the work never runs); `asyncio.create_task(...)` with the result dropped (the task can be
  garbage-collected mid-run and its exception is lost). JS/TS: `items.forEach(async (i) => await save(i))`
  (returns before any save completes); `items.map(async …)` whose result is not awaited;
  `return somePromise()` inside `try` with no `await` (a rejection skips the `catch`);
  `new Promise(async (resolve) => …)`; a fire-and-forget call in a handler without `.catch`.
- **Default severity:** major when the caller assumes the work is done (the response is sent before
  the write, errors vanish, C2/R1). When the un-awaited call is an **authorization or validation
  check**, file it as `PY-SEC-20` / `NODE-SEC-20` / `TS-SEC-20` (blocker, X-SEV-04). No finding for
  deliberate fire-and-forget with a stored task reference or a `.catch` that logs.
- **Why:** the statement after the call runs before, or without, the result.
- WRONG:
  ```python
  async def place_order(order: Order) -> None:
      await repo.save(order)
      send_confirmation(order)              # async def: creates a coroutine and discards it
      asyncio.create_task(sync_to_crm(order))   # reference dropped
  ```
  ```js
  async function importAll(rows) {
    rows.forEach(async (row) => { await db.insert(row); });   // resolves immediately
    return { imported: rows.length };
  }
  async function load(id) {
    try { return fetchUser(id); }                              // rejection bypasses the catch
    catch (err) { return null; }
  }
  ```
- CORRECT:
  ```python
  await send_confirmation(order)
  task = asyncio.create_task(sync_to_crm(order))
  background.add(task); task.add_done_callback(background.discard)
  ```
  ```js
  await Promise.all(rows.map((row) => db.insert(row)));
  async function load(id) {
    try { return await fetchUser(id); } catch (err) { return null; }
  }
  ```
- **Fix:** `await` it, `Promise.all` it, or keep the task reference and attach a done callback that
  logs; `for … of` with `await` when order matters.
- **Cite:** Python docs, `asyncio.create_task` (save a reference to avoid a task disappearing
  mid-execution); Python docs, "Coroutines and Tasks"; MDN, `Array.prototype.forEach` (does not
  wait for promises); ECMA-262, async function `return` semantics; CWE-252 (unchecked return
  value).
- **Tool code:** `[ruff: RUF006]`, `[mypy: unused-coroutine]`,
  `[typescript-eslint: no-floating-promises, no-misused-promises, return-await]`,
  `[eslint: no-async-promise-executor]`.

## 7. React state and effects

### TS-COR-11 — Stale closure and effect dependencies
- **Detect:** a prop, state or function read inside `useEffect` / `useCallback` / `useMemo` and
  missing from the dependency array (the corpus case: `useEffect(() => { load(productId) }, [])`);
  `// eslint-disable-next-line react-hooks/exhaustive-deps`; a `setInterval` or event listener set
  up once that reads state captured at mount; `setCount(count + 1)` twice in one handler or after
  an `await`; an object or function created in render listed as a dependency (the effect re-runs
  every render and can loop requests).
- **Default severity:** major (C2/R1: another entity's data stays on screen, a stale value is
  submitted, or a render loop floods the API). Blocker when the stale value is submitted to a
  payment or permission change.
- **Why:** each render's closure sees that render's values; an effect with the wrong list keeps
  seeing the old ones.
- WRONG:
  ```tsx
  useEffect(() => {
    fetchReviews(productId).then(setReviews);
  }, []);                                      // productId changes, reviews do not
  const onClick = () => { setCount(count + 1); setCount(count + 1); };   // adds 1, not 2
  ```
- CORRECT:
  ```tsx
  useEffect(() => {
    let ignore = false;
    fetchReviews(productId).then((r) => { if (!ignore) setReviews(r); });
    return () => { ignore = true; };
  }, [productId]);
  const onClick = () => { setCount((c) => c + 1); setCount((c) => c + 1); };
  ```
- **Fix:** list every reactive value; use the functional updater; move non-reactive values out of
  the component; let the lint rule drive the list and remove disables.
- **Cite:** React docs, "Synchronizing with Effects", "Removing Effect Dependencies",
  "Queueing a Series of State Updates".
- **Tool code:** `[eslint: react-hooks/exhaustive-deps]` (the tool reports a missing dependency;
  report disabled lines and custom hooks it does not know as model findings).

### TS-COR-12 — Out-of-order responses and effect cleanup
- **Detect:** a fetch in an effect keyed by a changing value (search text, tab, id) with no abort
  and no `ignore` flag, so a slow earlier response overwrites a newer one; `addEventListener`,
  `setInterval`, `subscribe` or `new WebSocket` in an effect with no cleanup return (duplicates
  stack up on every dependency change; React 18 Strict Mode shows it in development by running
  the effect twice).
- **Default severity:** major when stale results overwrite visible data (C2/R1); major for a
  per-render listener or timer leak; minor for a one-off listener on a long-lived component.
- **Why:** network replies arrive in any order, and effects re-run before the previous run is
  cleaned up.
- WRONG:
  ```tsx
  useEffect(() => {
    fetch(`/api/search?q=${q}`).then((r) => r.json()).then(setResults);   // "ab" can resolve after "abc"
    window.addEventListener('resize', onResize);                            // never removed
  }, [q]);
  ```
- CORRECT:
  ```tsx
  useEffect(() => {
    const ctrl = new AbortController();
    fetch(`/api/search?q=${encodeURIComponent(q)}`, { signal: ctrl.signal })
      .then((r) => r.json()).then(setResults)
      .catch((e) => { if (e.name !== 'AbortError') throw e; });
    window.addEventListener('resize', onResize);
    return () => { ctrl.abort(); window.removeEventListener('resize', onResize); };
  }, [q]);
  ```
- **Fix:** `AbortController` or an `ignore` flag; a cleanup function for everything the effect
  starts; prefer a data library (TanStack Query) that handles cancellation and caching.
- **Cite:** React docs, "Synchronizing with Effects" (fetching data, cleanup, Strict Mode);
  MDN, `AbortController`; CWE-772 (missing release of resource).
- **Tool code:** none.

### TS-COR-13 — Redundant state and wrong list keys
- **Detect:** `useState(props.value)` that is never reset when the prop changes;
  `useEffect(() => setFiltered(items.filter(…)), [items])` (state that can be computed in render);
  `key={index}` on a list that is sorted, filtered or has insertions or deletions and whose items
  hold state (inputs, expanded rows); `key={Math.random()}` (remounts every render); missing `key`.
- **Default severity:** major when the wrong row's input or state is shown or edited (C2/R1); minor
  otherwise.
- **Why:** React matches state to position and key; a second copy of the data goes stale.
- WRONG:
  ```tsx
  const [name, setName] = useState(user.name);        // a different user prop never updates the field
  {todos.map((t, i) => <TodoRow key={i} todo={t} />)}  // deleting row 1 gives row 2's state to row 3
  ```
- CORRECT:
  ```tsx
  <ProfileForm key={user.id} user={user} />            // reset by key; or compute from props
  {todos.map((t) => <TodoRow key={t.id} todo={t} />)}
  ```
- **Fix:** derive in render; reset with `key`; use stable ids from the data.
- **Cite:** React docs, "Rendering Lists" (keys), "Choosing the State Structure", "You Might Not
  Need an Effect".
- **Tool code:** `[eslint: react/no-array-index-key, react/jsx-key]`.

## 8. Comparisons and validation

### PY-COR-14 · NODE-COR-14 · TS-COR-14 — Comparison semantics
- **Detect:** JS: `[10, 9, 1].sort()` (sorts as strings: `[1, 10, 9]`); a comparator returning a
  boolean (`(a, b) => a > b`); `==` where coercion changes the result (X-SEV-08 sets the nit versus
  finding line); `date1 === date2` (reference equality); `x === NaN`; `Number('')` is `0`;
  `'admin,editor'.includes(role)` where a list was meant (`'edit'` passes). Python: `is` / `is not`
  with a literal or a value (works by accident for small ints and interned strings); `role in
  "admin,editor"` (substring test: `"edit" in "admin,editor"` is `True`); `x == None`.
- **Default severity:** minor for ordering and equality slips (C3); major when the result orders
  money or picks records (C2/R1); if the comparison **is** an authorization decision, it is a
  security finding (`PY-SEC-04` family, blocker per X-SEV-04).
- **Why:** the operator does something other than what the author reads.
- WRONG:
  ```js
  prices.sort();                                   // [5, 25, 100] becomes [100, 25, 5]: sorted as text
  if ('admin,editor'.includes(user.role)) allow();
  ```
  ```python
  if user.role in "admin,editor":                  # "edit", "min" and "" all pass
      allow()
  if status is "paid": ...                         # SyntaxWarning; identity, not equality
  ```
- CORRECT:
  ```js
  prices.sort((a, b) => a - b);
  if (['admin', 'editor'].includes(user.role)) allow();
  ```
  ```python
  if user.role in {"admin", "editor"}:
      allow()
  if status == "paid": ...
  ```
- **Fix:** numeric comparator; test membership in a collection; `==` for values, `is` only for
  `None` and singletons.
- **Cite:** MDN, `Array.prototype.sort` (default order is by UTF-16 string); ECMA-262,
  `IsLooselyEqual`; Python docs, "Comparisons" and "Membership test operations"; PEP 8,
  "Programming Recommendations"; CWE-697 (incorrect comparison).
- **Tool code:** `[ruff: F632, E711, E712]`, `[eslint: eqeqeq, use-isnan, no-compare-neg-zero]`.

### PY-COR-15 · NODE-COR-15 — Unanchored or stateful regex
- **Detect:** Python: `re.match(r'^\d+$', s)` accepts `"12\n"` (`$` also matches before a trailing
  newline); `re.match(r'\d+', s)` only tests the prefix (`"12abc"` passes); `re.search` used as a
  validator. JS: `/\d+/.test(s)` with no anchors; a regex with the `g` or `y` flag stored in a
  module constant and reused with `.test()` (`lastIndex` persists: `/a/g.test('a')` is `true`,
  then `false`, then `true`); `/^…$/m` used for single-line validation.
- **Default severity:** rate by what it guards. Guarding a sink (path, header, SQL fragment, URL,
  shell) is a security finding under the matching `-SEC-` rule. Guarding format only (a phone
  number, a code) is minor; major when the bypass lets bad data into storage.
- **Why:** the check passes values the author meant to reject, or alternates between pass and fail
  for the same input.
- WRONG:
  ```python
  if not re.match(r"^[a-z0-9_-]+$", slug):          # "ok\nSet-Cookie: x=1" passes
      abort(400)
  ```
  ```js
  const ID = /^[a-z0-9]+$/g;
  const isValid = (s) => ID.test(s);                 // true, false, true… for the same input
  ```
- CORRECT:
  ```python
  if not re.fullmatch(r"[a-z0-9_-]+", slug):
      abort(400)
  ```
  ```js
  const ID = /^[a-z0-9]+$/;                           // no g or y flag on a shared constant
  const isValid = (s) => ID.test(s);
  ```
- **Fix:** `re.fullmatch` or `\Z`; anchors on both ends; no `g`/`y` on shared regexes.
- **Cite:** Python docs, `re` (`$`, `fullmatch`); MDN, `RegExp.prototype.test` (`lastIndex` with
  `g`/`y`); OWASP Input Validation Cheat Sheet (anchor the pattern); CWE-185; CWE-20.
- **Tool code:** none.

## 9. Do not flag

| Pattern | Why it is not a finding |
|---|---|
| Mutable default that is never mutated and never escapes | latent only (X-SEV-01 minor); mention once at most |
| `float` for a ratio, percentage, metric, coordinate or timing | money rules apply to currency only |
| `datetime.now()` in a log line, a CLI banner or a local script | no stored or compared value |
| `Promise.all` with a `.map` over a small, fixed list | bounded; performance is a different ref |
| `useEffect` dependency lint hit with a deliberate comment that explains why | report only if the explanation is wrong |
| `==` between a string column and a string literal | X-SEV-08: nit |
| Missing null check where mypy strict or tsc strict is enabled and clean | the tool owns it |
| A race in code that runs in one process with one writer (a cron job) | question at most |
| `key={index}` on a static list that never reorders and holds no state | harmless |
| `Decimal` built from an `int` or a `str` | exact |
