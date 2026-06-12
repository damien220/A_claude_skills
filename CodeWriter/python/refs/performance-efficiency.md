# Performance & Efficiency — Python Reference

Grounded in the **CPython** data-structure/time-complexity docs, the `functools`/`itertools`/
`collections` docs, and community profiling guidance. Ruff `C4` and `PERF` flag several of these.
First rule: **measure before optimizing** — `timeit` for micro, `cProfile` for whole programs.

## Pick the data structure that makes the hot operation O(1)

Membership and de-duplication in a `list` are O(n); in a `set`/`dict` they are O(1) average.

| Operation | `list` | `set` / `dict` |
|---|---|---|
| `x in coll` | O(n) | O(1) avg |
| de-duplicate | O(n²) naive | O(n) |
| keyed lookup | O(n) scan | O(1) avg |

```python
# WRONG — O(n) membership inside an O(m) loop ⇒ O(n·m) (ruff PERF: in-list lookup)
seen = []
for item in stream:
    if item not in seen:        # linear scan every iteration
        seen.append(item)
```

```python
# CORRECT — O(1) membership
seen: set[str] = set()
for item in stream:
    if item not in seen:
        seen.add(item)
```

Use the right specialized container: `collections.Counter` for tallies, `collections.deque` for
O(1) ends (a `list.pop(0)` is O(n)), `dict.setdefault` / `defaultdict` for grouping.

```python
from collections import Counter, defaultdict, deque

counts = Counter(words)                       # not a hand-rolled dict++ loop
groups: dict[str, list[int]] = defaultdict(list)
for key, val in pairs:
    groups[key].append(val)
queue = deque(maxlen=1000)                     # O(1) append/popleft
```

## Comprehensions and generators over manual loops

Comprehensions are clearer and faster than `append` loops (ruff `C4`/`PERF`). Use a **generator**
when you don't need the whole sequence materialized — it streams and bounds memory.

```python
# WRONG                                     # CORRECT
out = []                                     out = [x * 2 for x in xs if x > 0]
for x in xs:
    if x > 0:
        out.append(x * 2)
```

```python
# Generator: process a huge/infinite source without building a giant list
def parse_lines(path: str):
    with open(path) as f:
        for line in f:                       # streams one line at a time
            yield parse(line)

total = sum(rec.amount for rec in parse_lines(path))   # constant memory
```

Don't build a list only to consume it once — pass the generator straight to `sum`/`any`/`max`/
`join`. But *do* materialize when you iterate multiple times (a generator is exhausted after one pass).

## Reach for builtins and the stdlib

Builtins run in C and beat hand-rolled equivalents. Prefer `sum`, `min`/`max` (with `key=`),
`any`/`all`, `sorted`, `map`/`filter`, and `itertools`/`functools` over manual loops.

```python
# WRONG                                     # CORRECT
total = 0                                    total = sum(values)
for v in values: total += v

found = False                                found = any(p(x) for x in xs)
for x in xs:
    if p(x): found = True; break
```

## String building: `join`, not `+=` in a loop

Repeated `+=` on `str` is O(n²) (each step copies the whole string). Collect parts and `join` once.

```python
# WRONG                                     # CORRECT
s = ""                                        s = "".join(str(p) for p in parts)
for p in parts:
    s += str(p)
```

## Cache repeated work

`functools.cache` / `lru_cache` memoizes pure functions; `functools.cached_property` memoizes a
computed attribute. Only cache pure, hashable-argument functions — caching impure functions hides bugs.

```python
from functools import cache, cached_property

@cache
def factorial(n: int) -> int:               # repeated calls are free after the first
    return 1 if n <= 1 else n * factorial(n - 1)

class Report:
    def __init__(self, rows: list[Row]) -> None:
        self._rows = rows

    @cached_property
    def total(self) -> int:                  # computed once, then reused
        return sum(r.amount for r in self._rows)
```

## Avoid premature and micro-optimization

Optimize the algorithm (big-O) before the constant factor; optimize the *hot path* the profiler
points at, not guesses. Readability wins until a measurement says otherwise. Local-variable
binding of a hot attribute/method is a last-resort micro-tweak — reserve it for proven inner loops.

## Profiling — measure first

Never optimize without data. Choose the profiler that matches the bottleneck type:

| Tool | What it finds | How to use |
|---|---|---|
| `cProfile` (stdlib) | Which functions are called most and cost the most total time | `python -m cProfile -s cumulative myapp.py` |
| `py-spy` | Same as cProfile but attaches to a **live** running process; no code changes | `py-spy top --pid <PID>` |
| `line_profiler` | Line-by-line timing inside a specific function (add `@profile` decorator) | `kernprof -l -v myscript.py` |
| `memory-profiler` | Memory usage line-by-line; diagnoses leaks and unexpected copies | `python -m memory_profiler myscript.py` |

```bash
# Quick workflow: profile in dev; check the top-5 hot functions
python -m cProfile -s cumulative -o prof.out myapp.py
python -c "import pstats; p = pstats.Stats('prof.out'); p.strip_dirs().sort_stats('cumulative').print_stats(10)"

# Attach to a live server without restarting (requires py-spy)
pip install py-spy
sudo py-spy top --pid $(pgrep -f uvicorn)

# Line-level profiling of a specific bottleneck
pip install line_profiler
# decorate the function: @profile (no import needed, kernprof injects it)
kernprof -l -v my_hot_function.py
```

**Rule:** Gather profiling data from a production-like load test (e.g. `locust` or `k6`), not from
a warm-up run in dev. Micro-benchmarks (`timeit`) are only valid for comparing two implementations
of the same algorithm in isolation.

## Redis caching patterns — distributed caching for web services

`functools.cache` is process-local and single-process. For multi-worker deployments (Gunicorn,
Kubernetes pods) use Redis (via `cache_manager` from Dev_util_prj or raw `redis-py`).

### Cache-aside (lazy loading)

```python
# WRONG — no cache; DB hit on every request
async def get_user(user_id: str) -> dict:
    return await db.fetchone('SELECT * FROM users WHERE id = $1', user_id)
```

```python
# CORRECT — cache-aside with TTL
import json
import redis.asyncio as aioredis

redis = aioredis.from_url('redis://localhost:6379')

async def get_user(user_id: str) -> dict:
    cache_key = f'user:{user_id}'
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    user = await db.fetchone('SELECT * FROM users WHERE id = $1', user_id)
    await redis.set(cache_key, json.dumps(user), ex=300)  # 5-minute TTL
    return user
```

### Cache invalidation — version key pattern

Deleting individual keys under concurrent writes leads to stale reads or race conditions.
Increment a version counter on mutation; embed the version in all related cache keys.

```python
# WRONG — delete key on update; concurrent readers may read stale or miss entirely
async def update_user(user_id: str, data: dict) -> None:
    await db.execute('UPDATE users SET ... WHERE id = $1', user_id)
    await redis.delete(f'user:{user_id}')   # race: between delete and next write
```

```python
# CORRECT — version-based invalidation; old keys expire naturally
VERSION_KEY = 'user_version'

async def cache_key_for(user_id: str) -> str:
    version = await redis.get(VERSION_KEY) or b'1'
    return f'user:{user_id}:v{version.decode()}'

async def update_user(user_id: str, data: dict) -> None:
    await db.execute('UPDATE users SET ... WHERE id = $1', user_id)
    await redis.incr(VERSION_KEY)   # all existing cache keys are now "old version"
```

### Stale-while-revalidate — serve stale while refreshing in the background

```python
import asyncio
import time

SOFT_TTL = 60    # serve from cache for 60s
HARD_TTL = 120   # evict from Redis after 120s (never serve beyond this age)

async def get_user_swr(user_id: str) -> dict:
    raw = await redis.get(f'user:{user_id}:swr')
    if raw:
        payload = json.loads(raw)
        age = time.time() - payload['cached_at']
        if age < SOFT_TTL:
            return payload['data']                    # fresh: return immediately
        if age < HARD_TTL:
            asyncio.create_task(_refresh_user(user_id))   # stale: serve + refresh async
            return payload['data']

    return await _refresh_user(user_id)               # cache miss: fetch synchronously

async def _refresh_user(user_id: str) -> dict:
    user = await db.fetchone('SELECT * FROM users WHERE id = $1', user_id)
    await redis.set(
        f'user:{user_id}:swr',
        json.dumps({'data': user, 'cached_at': time.time()}),
        ex=HARD_TTL,
    )
    return user
```

### Cache stampede prevention — distributed lock before DB fetch

Under heavy load a cache miss can cause dozens of concurrent goroutines to all hit the DB at once.

```python
import asyncio

LOCK_TTL = 5   # seconds; must cover worst-case DB query time

async def get_user_safe(user_id: str) -> dict:
    cache_key = f'user:{user_id}'
    lock_key  = f'user:{user_id}:lock'

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # Try to acquire the "refetch" lock
    acquired = await redis.set(lock_key, '1', nx=True, ex=LOCK_TTL)
    if acquired:
        # We hold the lock — fetch and populate
        try:
            user = await db.fetchone('SELECT * FROM users WHERE id = $1', user_id)
            await redis.set(cache_key, json.dumps(user), ex=300)
            return user
        finally:
            await redis.delete(lock_key)
    else:
        # Another worker is fetching; wait briefly then retry
        await asyncio.sleep(0.05)
        return await get_user_safe(user_id)
```

**Prefer `cache_manager` from Dev_util_prj** — it implements cache-aside, multi-layer caches, and
TTL eviction behind the `@cached` decorator. Use raw Redis only when you need the version or SWR
patterns above, which require direct key manipulation.

## Dev_util_prj — `cache_manager`

`cache_manager` provides caching backends (memory, file, SQLite, Redis, MongoDB), eviction policies
(LRU/LFU/FIFO), `@cached` and `@llm_cache` decorators, multi-layer caches, and LLM-aware key
building — all behind a single unified interface.

**Install (clone from source):**
```bash
git clone <CACHE_MANAGER_GITHUB_URL>   # fill URL in Dev_util_prj/Packages/Cache_manager/pyproject.toml [project.urls]
cd Cache_manager && pip install -e .
```

```python
from cache_manager import create_cache, cached

cache = create_cache("memory", max_size=1000, eviction_policy="lru")

@cached(cache, ttl=300)
async def fetch_user(user_id: str) -> dict:
    return await db.get(user_id)
```
