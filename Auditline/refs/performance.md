# Performance

Sources: Node.js docs ("Don't Block the Event Loop"); Python docs (`asyncio`, `functools`,
`collections`); Django, SQLAlchemy and Prisma docs; PostgreSQL docs; React and Next.js docs;
web.dev; OWASP API Security Top 10 2023; MITRE CWE as cited per rule.

## Contents

1. How to use this ref
2. Rule map
3. Data access: PERF-01, PERF-07, PERF-08
4. Event loop and concurrency: PERF-02, PERF-03, PERF-04
5. Memory and algorithms: PERF-05, PERF-06, PERF-11
6. Frontend: PERF-09, PERF-10
7. Do not flag

## 1. How to use this ref

- **Rule IDs.** `<LANG>-PERF-NN`; the number is the concept across languages. `PY-PERF-01` is the
  N+1 query the P1 sample report uses.
- **Rate by growth and path, not by pattern.** Work that grows with data the author does not control
  (rows per customer, items per upload, requests per second) on a request path is C2/R1: major.
  The same code over a constant, an enum or a hard-capped page is D2: minor or silence. Name the
  `n` in `why` ("one query per unbilled order; orders per customer are unbounded").
- **Setup and scripts are exempt.** A synchronous call at module load, in a CLI, a migration or a
  test is not on a request path (R3, nit at most).
- **No measurements, no hunches.** Do not claim a percentage or a speed-up. State the complexity
  or the number of round trips. A micro-optimisation with no stated growth is silence.
- **Severity anchors.** X-SEV-02 settles the level of query or call per item; this ref adds the
  detection variants and the other patterns.

## 2. Rule map

| ID | Defect | Languages | Default severity |
|---|---|---|---|
| PERF-01 | Query or remote call per item (N+1) | PY, NODE, TS | major (X-SEV-02) |
| PERF-02 | Blocking call in async or request code | PY, NODE | major on a request path |
| PERF-03 | Sequential awaits of independent calls | PY, NODE, TS | minor; major with 3+ slow calls |
| PERF-04 | Unbounded concurrency | PY, NODE, TS | major if size is unbounded |
| PERF-05 | Unbounded memory | PY, NODE | major if size is user-controlled |
| PERF-06 | Quadratic loops | PY, NODE, TS | major if `n` is data-controlled |
| PERF-07 | Query shape: scan, deep offset, `SELECT *` | PY, NODE | minor; major with proof |
| PERF-08 | Client or connection created per request | PY, NODE | major for DB; minor for HTTP |
| PERF-09 | Re-render cost and long lists | TS | minor; major if unbounded list |
| PERF-10 | Import cost and bundle size | TS | minor |
| PERF-11 | Catastrophic regex backtracking | PY, NODE | major |

## 3. Data access

### PY-PERF-01 · NODE-PERF-01 · TS-PERF-01 — Query or remote call per item (N+1)
- **Detect:** X-SEV-02 lists the explicit forms (a query, `fetch` or `await` inside a loop). Also:
  an ORM relation read inside a loop or comprehension (`order.customer.name`, `post.author`,
  `invoice.lines.all()` with no `select_related` / `prefetch_related` / `joinedload` /
  `selectinload` / `include`); a serializer, template or GraphQL resolver that loads a relation per
  parent (needs a DataLoader); a React list row component that calls `useQuery` / `fetch` for its
  own author; `Promise.all(rows.map((r) => db.user.findUnique(...)))` (concurrent, still N queries).
- **Default severity:** per X-SEV-02: major on a request path or over data that grows; minor
  over a small bounded collection.
- **Why:** each item adds a round trip; 500 orders mean 501 queries per request.
- WRONG:
  ```python
  orders = Order.objects.filter(status="unbilled")
  rows = [{"id": o.id, "customer": o.customer.name} for o in orders]   # one query per order
  ```
  ```js
  const authors = await Promise.all(
    posts.map((p) => prisma.user.findUnique({ where: { id: p.authorId } })));   // N queries
  ```
- CORRECT:
  ```python
  orders = Order.objects.filter(status="unbilled").select_related("customer")
  ```
  ```js
  const posts = await prisma.post.findMany({ include: { author: true } });
  // or one query for the set:
  const authors = await prisma.user.findMany({ where: { id: { in: posts.map((p) => p.authorId) } } });
  ```
- **Fix:** `select_related` (to-one) / `prefetch_related` (to-many) / `selectinload` / `include`;
  `WHERE id IN (…)`; a DataLoader per request in GraphQL; a batch endpoint for the browser.
- **Cite:** CWE-1073; Django docs, "Database access optimization"; SQLAlchemy docs,
  "Relationship Loading Techniques"; Prisma docs, "Relation queries"; `graphql/dataloader` README.
- **Tool code:** `[eslint: no-await-in-loop]` flags the explicit loop only and also fires on
  loops that must be sequential; the ORM forms are model findings.

### PY-PERF-07 · NODE-PERF-07 — Query shape: scan, deep offset, over-fetch
- **Detect:** only when the schema, migration or model is in the diff or file: a filter, join or
  `ORDER BY` column with no index in the visible migration; `WHERE lower(email) = $1` with no
  expression index; `LIKE '%term%'` (a leading wildcard cannot use a B-tree); `OFFSET 100000` deep
  pagination; `SELECT *` or a model load that pulls large text/blob columns for a list view;
  `if len(qs) > 0` / `.count() > 0` instead of `.exists()`; `ORDER BY` with no `LIMIT` on a table
  that grows.
- **Default severity:** minor for `SELECT *` and count-for-existence (C3). Major only when the
  table grows with users and the diff shows the missing index (C2/R1). If the index may exist
  outside the diff, a question (X-SEV-09).
- **Why:** the database reads every row, or builds and discards a large offset, for each request.
- WRONG:
  ```python
  if len(Order.objects.filter(customer_id=cid)):          # loads every row to test existence
      ...
  rows = db.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 20 OFFSET %s", (page * 20,))
  ```
- CORRECT:
  ```python
  if Order.objects.filter(customer_id=cid).exists():
      ...
  rows = db.execute(
      "SELECT id, kind, created_at FROM events WHERE created_at < %s ORDER BY created_at DESC LIMIT 20",
      (cursor,))                                           # keyset pagination
  ```
- **Fix:** add the index in the same change; `.exists()` / `EXISTS`; keyset pagination; select
  only the columns the view uses; `pg_trgm` for substring search.
- **Cite:** PostgreSQL docs, "Indexes" (Index Types, Indexes on Expressions, Indexes and ORDER
  BY); Django docs, `QuerySet.exists()`; Use The Index, Luke, "Paging Through Results".
- **Tool code:** none.

### PY-PERF-08 · NODE-PERF-08 — Client or connection created per request
- **Detect:** inside a handler or a function it calls: `new Pool(...)`, `new PrismaClient()`,
  `new Redis(...)`, `new S3Client(...)`, `psycopg2.connect(...)`, `create_engine(...)`,
  `boto3.client(...)`, `httpx.Client()`, or repeated bare `requests.get(...)` where a `Session`
  would reuse connections. Module-scope construction (also in serverless, where warm invocations
  reuse it) is correct.
- **Default severity:** major for database clients and pools (C2/R1: every request opens
  connections until the server refuses them); minor for HTTP clients.
- **Why:** a new client repeats DNS, TCP and TLS setup and bypasses the pool's limit.
- WRONG:
  ```js
  app.get('/users/:id', async (req) => {
    const pool = new Pool({ connectionString: process.env.DATABASE_URL });   // one pool per request
    return (await pool.query('SELECT * FROM users WHERE id = $1', [req.params.id])).rows[0];
  });
  ```
- CORRECT:
  ```js
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });     // once per process
  app.get('/users/:id', async (req) =>
    (await pool.query('SELECT id, name FROM users WHERE id = $1', [req.params.id])).rows[0]);
  ```
- **Fix:** build the client at module or application scope and inject it; close it on shutdown.
- **Cite:** node-postgres docs, "Pooling"; SQLAlchemy docs, "Engine Configuration" (one engine per
  database URL per process); Prisma docs, "Best practice for instantiating PrismaClient";
  Requests docs, "Session Objects".
- **Tool code:** none.

## 4. Event loop and concurrency

### PY-PERF-02 · NODE-PERF-02 — Blocking call in async or request code
- **Detect:** Python, inside `async def`: `requests.*`, `time.sleep`, `open(...).read()`,
  `subprocess.run`, a synchronous DB driver call, CPU work (`bcrypt.hashpw`, `hashlib.pbkdf2_hmac`,
  image or PDF processing, `json.loads` of megabytes). Node, in a handler, hook or consumer:
  `fs.readFileSync`, `execSync`, `bcrypt.hashSync`, `crypto.pbkdf2Sync` / `scryptSync`, a
  synchronous loop over a large array, `JSON.parse` of a multi-megabyte body.
- **Default severity:** major in a request handler (C2/R1: every concurrent request waits). Minor
  when the work is small and bounded. No finding at module load, in a CLI or a migration.
- **Why:** one event loop thread serves all requests; a call that holds it stops them all.
- WRONG:
  ```python
  @app.get("/rates")
  async def rates() -> dict:
      resp = requests.get(RATES_URL, timeout=5)          # blocks the event loop
      return resp.json()
  ```
  ```js
  app.post('/signup', async (req, reply) => {
    const hash = bcrypt.hashSync(req.body.password, 12);   // ~250 ms of blocked loop per signup
  });
  ```
- CORRECT:
  ```python
  async with httpx.AsyncClient(timeout=5) as client:
      resp = await client.get(RATES_URL)
  digest = await asyncio.to_thread(hash_password, password)   # CPU or unavoidable sync call
  ```
  ```js
  const hash = await bcrypt.hash(req.body.password, 12);      // runs on the libuv pool
  ```
- **Fix:** the async API of the same library; `asyncio.to_thread` / `run_in_executor`; worker
  threads for CPU work in Node.
- **Cite:** Node.js docs, "Don't Block the Event Loop (or the Worker Pool)"; Python docs,
  `asyncio` "Running blocking code" and `asyncio.to_thread`.
- **Tool code:** `[ruff: ASYNC210, ASYNC230, ASYNC251]`, `[eslint: n/no-sync]`.

### PY-PERF-03 · NODE-PERF-03 · TS-PERF-03 — Sequential awaits of independent calls
- **Detect:** `const a = await getA(); const b = await getB();` where `getB` does not use `a`;
  Python `x = await f(); y = await g()` likewise. Typical in handlers that load a user, their
  orders and their settings.
- **Default severity:** minor (C3: latency is the sum instead of the maximum). Major when three or
  more slow remote calls sit on a hot request path.
- **Why:** each await waits for the previous round trip.
- WRONG:
  ```js
  const user = await getUser(id);
  const orders = await getOrders(id);          // does not depend on user
  const prefs = await getPrefs(id);
  ```
- CORRECT:
  ```js
  const [user, orders, prefs] = await Promise.all([getUser(id), getOrders(id), getPrefs(id)]);
  ```
  ```python
  async with asyncio.TaskGroup() as tg:
      user = tg.create_task(get_user(uid)); orders = tg.create_task(get_orders(uid))
  ```
- **Fix:** `Promise.all` / `Promise.allSettled`; `asyncio.gather` / `TaskGroup` (3.11+).
- **Cite:** MDN, `Promise.all`; Python docs, `asyncio.TaskGroup`.
- **Tool code:** none.

### PY-PERF-04 · NODE-PERF-04 · TS-PERF-04 — Unbounded concurrency
- **Detect:** `Promise.all(items.map(...))` or `asyncio.gather(*[... for x in items])` where the
  list comes from a table, an upload or user input and each task does I/O (a query, an HTTP call,
  an email). Also an unbounded `for … of` that spawns un-awaited tasks.
- **Default severity:** major when the count is unbounded (U3): the pool is exhausted or the
  provider rate-limits and the whole batch fails. Minor over a small constant list.
- **Why:** 5,000 tasks start at once; the pool (10 connections by default in node-postgres) queues
  them, sockets run out, and one failure rejects the whole `Promise.all`.
- WRONG:
  ```js
  await Promise.all(users.map((u) => sendEmail(u)));       // users: every row in the table
  ```
  ```python
  await asyncio.gather(*(fetch(url) for url in urls))       # urls: from the request body
  ```
- CORRECT:
  ```js
  import pLimit from 'p-limit';
  const limit = pLimit(10);
  await Promise.all(users.map((u) => limit(() => sendEmail(u))));
  ```
  ```python
  sem = asyncio.Semaphore(10)
  async def bounded(url: str) -> Response:
      async with sem:
          return await fetch(url)
  await asyncio.gather(*(bounded(u) for u in urls))
  ```
- **Fix:** a concurrency limit (`p-limit`, `Semaphore`), batches, a queue; cap the input size.
- **Cite:** CWE-770 (allocation of resources without limits); CWE-400; OWASP API Security Top 10
  2023, API4 Unrestricted Resource Consumption; Python docs, `asyncio.Semaphore`; node-postgres
  docs, "Pooling" (`max`).
- **Tool code:** none.

## 5. Memory and algorithms

### PY-PERF-05 · NODE-PERF-05 — Unbounded memory
- **Detect:** `f.read()`, `readFileSync`, `await res.json()` / `res.text()` / `request.body` of an
  upload or remote body with no size cap; `list(queryset)`, `.all()`, `findMany()` or a raw
  `SELECT` with no `LIMIT` in a list endpoint; iterating a large queryset without
  `.iterator()`; building a whole export in memory instead of streaming; a module-level `dict` /
  `Map` / array that grows per request (cache with no TTL or bound, listener list, session store);
  `@lru_cache` on an instance method (it keeps `self` alive) or `maxsize=None` on a function keyed
  by user input.
- **Default severity:** major when the size is user-controlled or grows (U3): one large request
  or enough requests exhaust memory (C2/R1). Minor for bounded data.
- **Why:** memory use grows with input, and the process is killed or swaps.
- WRONG:
  ```python
  @bp.get("/export")
  def export() -> Response:
      rows = Order.query.all()                                  # every order, then a full CSV string
      return Response(to_csv(rows), mimetype="text/csv")
  seen: dict[str, Result] = {}                                  # module level, keyed by request input
  ```
  ```js
  const body = await readFile(req.query.path);                  // whole file in memory
  const cache = new Map(); app.get('/q/:k', (req) => cache.set(req.params.k, compute(req.params.k)));
  ```
- CORRECT:
  ```python
  def export() -> Response:
      def generate():
          for order in Order.query.yield_per(1000):
              yield to_csv_row(order)
      return Response(generate(), mimetype="text/csv")
  ```
  ```js
  await pipeline(createReadStream(file), reply.raw);            // stream; bounded memory
  const cache = new LRUCache({ max: 500, ttl: 60_000 });        // bounded cache
  ```
- **Fix:** stream; paginate with a hard cap; `maxsize` and TTL on caches; limit body size at the
  framework.
- **Cite:** CWE-770; CWE-400; CWE-401; OWASP API4:2023; Python docs, `functools.lru_cache`
  (`maxsize`); Django docs, `QuerySet.iterator()`; Node.js docs, `stream.pipeline`.
- **Tool code:** `[ruff: B019]` (cached instance method only).

### PY-PERF-06 · NODE-PERF-06 · TS-PERF-06 — Quadratic loops
- **Detect:** `if x in some_list` / `array.includes(x)` / `array.find(...)` inside a loop over a
  similar-sized collection; a nested loop that joins two lists by id; `reduce` with a spread
  accumulator (`({ ...acc, [k]: v })`, `[...acc, x]`) which copies every step; Python
  `list.insert(0, x)` / `list.pop(0)` in a loop; `.filter(...)` inside `.map(...)`.
- **Default severity:** major when `n` is controlled by data or users on a request path (U3), e.g.
  20,000 items; minor when `n` is bounded and small (D2). State `n` and the complexity.
- **Why:** cost grows with the square of the input: a membership test on a 20,000-element list is
  thousands of times slower than on a set, and a reduce-spread over 20,000 items copies 200
  million entries.
- WRONG:
  ```python
  new_ids = [i for i in incoming_ids if i not in existing_ids]    # existing_ids is a list: O(n·m)
  ```
  ```js
  const byId = rows.reduce((acc, r) => ({ ...acc, [r.id]: r }), {});   // O(n²)
  const withOwner = orders.map((o) => ({ ...o, owner: users.find((u) => u.id === o.userId) }));   // O(n·m)
  ```
- CORRECT:
  ```python
  existing = set(existing_ids)
  new_ids = [i for i in incoming_ids if i not in existing]
  ```
  ```js
  const byId = new Map(rows.map((r) => [r.id, r]));
  const usersById = new Map(users.map((u) => [u.id, u]));
  const withOwner = orders.map((o) => ({ ...o, owner: usersById.get(o.userId) }));
  ```
- **Fix:** build a `set` / `dict` / `Map` once; `collections.deque` for queues; push into one
  accumulator instead of copying.
- **Cite:** CWE-407 (inefficient algorithmic complexity); Python Wiki, "TimeComplexity"; Python
  docs, `collections.deque`; MDN, spread syntax.
- **Tool code:** none.

### PY-PERF-11 · NODE-PERF-11 — Catastrophic regex backtracking
- **Detect:** a regex with nested quantifiers or overlapping alternatives, applied to a value
  from a request, a file or a third party: `(a+)+$`, `(\w+\s?)*$`, `(.*)*`, `(a|a)*`,
  `^(([a-z])+.)+[A-Z]([a-z])+$`. The input needs no special privilege, only a long string that
  almost matches.
- **Default severity:** major (C2/R1: one request pins a CPU; in Node it stalls every request).
  Minor when the input has a small hard length cap before the match.
- **Why:** backtracking engines try exponentially many splits on a near-match. Measured here:
  `(a+)+$` against 27 `a`s and a final `b` takes about 4 s in Python and 1.2 s in V8, and each
  extra character doubles it.
- WRONG:
  ```python
  if re.match(r"^(\w+\s?)*$", request.args["title"]):     # "aaaa…a!" never finishes
      ...
  ```
  ```js
  const ok = /^(([a-z])+.)+[A-Z]([a-z])+$/.test(req.query.name);
  ```
- CORRECT:
  ```python
  if len(title) <= 200 and re.fullmatch(r"[\w ]*", title):    # unambiguous pattern plus a length cap
      ...
  ```
  ```js
  import RE2 from 're2';                                       // linear-time engine
  const ok = new RE2('^[a-z]+[A-Z][a-z]+$').test(String(req.query.name).slice(0, 200));
  ```
- **Fix:** rewrite so each character can match one way; cap the input length first; use RE2
  (`google-re2`, `re2`) for user-supplied patterns or when the pattern cannot be simplified.
- **Cite:** CWE-1333; OWASP, "Regular expression Denial of Service (ReDoS)"; Node.js docs,
  "Don't Block the Event Loop" (section on ReDoS).
- **Tool code:** `[eslint: security/detect-unsafe-regex]` (noisy; confirm that the input is
  untrusted before reporting).

## 6. Frontend

### TS-PERF-09 — Re-render cost and long lists
- **Detect:** only with evidence of cost: an inline object, array or function passed as a prop to a
  `React.memo` child (the memo never hits); a context provider with `value={{ … }}` rebuilt on
  every render that many components read; a component defined inside another component (it
  remounts on every render); form input state kept in a top-level component so each keystroke
  renders the page; a sort or filter over thousands of items in render with no `useMemo`; an
  API-sized list rendered row by row with no pagination or virtualization; an effect that sets
  state which triggers another render of the same tree.
- **Default severity:** minor (C3). Major when the list is unbounded (U3) or the interaction is
  visibly slow on the main flow (typing lag).
- **Why:** the cost is paid on every keystroke or update by every user of that screen.
- WRONG:
  ```tsx
  function Page({ rows }: { rows: Row[] }) {
    const Toolbar = () => <Filters />;                            // new component type each render
    return <><Toolbar /><Table rows={rows} style={{ width: 600 }} onSelect={(r) => select(r)} /></>;
  }                                                               // Table is memo'd; props change every render
  ```
- CORRECT:
  ```tsx
  const Toolbar = () => <Filters />;                              // defined at module scope
  const tableStyle = { width: 600 };
  function Page({ rows }: { rows: Row[] }) {
    const onSelect = useCallback((r: Row) => select(r), [select]);
    return <><Toolbar /><Table rows={rows} style={tableStyle} onSelect={onSelect} /></>;
  }
  ```
- **Fix:** hoist components and constants; `useMemo` / `useCallback` only where a memoized child or
  a measured computation needs it; move state down; paginate or virtualize (`react-window`).
- **Cite:** React docs, `memo`, `useMemo` ("only rely on `useMemo` as a performance optimization"),
  `useCallback`; web.dev, "Virtualize large lists with react-window".
- **Tool code:** `[eslint: react/no-unstable-nested-components, react/jsx-no-constructed-context-values]`.

### TS-PERF-10 — Import cost and bundle size
- **Detect:** `import _ from 'lodash'` or `import moment from 'moment'` for one function; an
  import from a large barrel file in client code; a server-only or Node-only dependency imported
  into a `'use client'` module; a heavy rarely-used library (chart, editor, PDF) imported
  statically into the first route; `'use client'` placed at the top of a large tree.
- **Default severity:** minor (C3). Without a size measurement, say so in `why` and keep it minor.
- **Why:** everything imported statically ships in the initial JavaScript every visitor downloads.
- WRONG:
  ```tsx
  import _ from 'lodash';
  import { Chart } from 'heavy-charts';              // first route, used only on the Reports tab
  const names = _.uniq(users.map((u) => u.name));
  ```
- CORRECT:
  ```tsx
  import uniq from 'lodash-es/uniq';
  const Chart = lazy(() => import('./Chart'));       // or next/dynamic in Next.js
  const names = uniq(users.map((u) => u.name));
  ```
- **Fix:** per-function imports from an ES-module build; dynamic import for heavy, rarely used
  components; keep `'use client'` at leaf components.
- **Cite:** web.dev, "Reduce JavaScript payloads with code splitting"; Next.js docs, "Lazy
  Loading"; webpack docs, "Tree Shaking".
- **Tool code:** `[eslint: no-restricted-imports]` when the project configures it.

## 7. Do not flag

| Pattern | Why it is not a finding |
|---|---|
| A query per item over a constant or enum list | D2: bounded and small (X-SEV-02 minor) |
| `*Sync` filesystem calls at module load, in a CLI or in tests | not on a request path |
| `useMemo` / `useCallback` missing on a cheap computation or an un-memoized child | premature; the docs call them optimizations |
| `Promise.all` over a handful of fixed calls | bounded |
| A missing index when the migration is not in the diff | question at most (X-SEV-09) |
| `lru_cache` on a pure module-level function with a bounded input domain | bounded |
| Sequential awaits where order or rate limits matter, or the second call uses the first result | dependent |
| Anything described as "faster" with no growth argument | opinion, not a finding |
