# Sync vs Async & Concurrency — Python Reference

Grounded in the **asyncio** docs, **PEP 654** (exception groups / structured concurrency), and the
`concurrent.futures` / `threading` / `multiprocessing` docs. The GIL is the backdrop: choose the
concurrency model that matches whether the work is I/O-bound or CPU-bound.

## The decision

| Workload                                                                 | Tool                                      | Why                                                        |
| ------------------------------------------------------------------------ | ----------------------------------------- | ---------------------------------------------------------- |
| Many concurrent **I/O** waits (HTTP, DB, sockets), library has async API | `asyncio`                                 | one thread multiplexes thousands of waits; lowest overhead |
| Blocking **I/O** with only a sync library                                | `ThreadPoolExecutor` / `threading`        | threads release the GIL while blocked on I/O               |
| **CPU-bound** work (parsing, math, compression)                          | `ProcessPoolExecutor` / `multiprocessing` | sidesteps the GIL with separate processes                  |
| Mostly sequential, no waiting                                            | plain sync                                | concurrency adds only complexity                           |

**async is not "faster Python."** It helps only when the program spends time _waiting_ on I/O and
you have an async-capable library. For CPU work, async makes things slower.

## Never block the event loop

A coroutine must not call a blocking function — `time.sleep`, synchronous `requests`, blocking
file reads, or a heavy CPU loop. One blocking call freezes _every_ concurrent task.

```python
# WRONG — blocking calls inside a coroutine stall the whole loop
import time, requests

async def fetch(url: str) -> bytes:
    time.sleep(1)                       # blocks the event loop for 1s
    return requests.get(url).content    # synchronous I/O blocks every other task
```

```python
# CORRECT — await async equivalents
import asyncio
import httpx

async def fetch(client: httpx.AsyncClient, url: str) -> bytes:
    await asyncio.sleep(1)
    resp = await client.get(url, timeout=10.0)
    return resp.content
```

For unavoidable blocking/CPU work inside async code, offload it so the loop stays free:

```python
import asyncio

async def crunch(data: bytes) -> int:
    # runs in a thread (I/O) or use a process pool for CPU; loop keeps serving other tasks
    return await asyncio.to_thread(expensive_sync_parse, data)
```

## Run awaits concurrently, not serially

Awaiting in a loop serializes the waits. Use `asyncio.gather` (or `TaskGroup`) to overlap them.

```python
# WRONG — total time = sum of all requests
async def fetch_all(client, urls):
    results = []
    for url in urls:
        results.append(await client.get(url))   # each await finishes before the next starts
    return results
```

```python
# CORRECT — total time ≈ the slowest single request
async def fetch_all(client: httpx.AsyncClient, urls: list[str]) -> list[httpx.Response]:
    return await asyncio.gather(*(client.get(url, timeout=10.0) for url in urls))
```

## Structured concurrency with `TaskGroup` (3.11+)

`asyncio.TaskGroup` is the modern default for spawning child tasks: it awaits them all on exit and,
if one fails, cancels the siblings and raises an `ExceptionGroup` (PEP 654). Prefer it over bare
`create_task` (whose exceptions can vanish if the task is never awaited).

```python
async def process(urls: list[str]) -> list[bytes]:
    results: list[bytes] = []
    async with httpx.AsyncClient() as client:
        async with asyncio.TaskGroup() as tg:        # cancels siblings on first failure
            tasks = [tg.create_task(fetch(client, u)) for u in urls]
    return [t.result() for t in tasks]
```

## Threads vs processes (sync world)

Use `concurrent.futures` executors rather than managing threads/processes by hand.

```python
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

# I/O-bound: threads release the GIL while waiting
with ThreadPoolExecutor(max_workers=16) as pool:
    bodies = list(pool.map(download, urls))

# CPU-bound: separate processes dodge the GIL
with ProcessPoolExecutor() as pool:
    digests = list(pool.map(hash_file, paths))
```

## Cancellation, timeouts, and cleanup

Bound every awaited I/O with a timeout, and release resources with `async with`.

```python
async def fetch_bounded(client: httpx.AsyncClient, url: str) -> bytes:
    try:
        async with asyncio.timeout(5):          # 3.11+; raises TimeoutError on overrun
            resp = await client.get(url)
            return resp.content
    except TimeoutError:
        raise                                    # let the caller decide; don't swallow
```

Don't fire-and-forget: keep a reference to every `create_task` result (or use `TaskGroup`) so
exceptions surface and tasks aren't garbage-collected mid-flight.

## Dev_util_prj — async and concurrency

### `event_dispatcher`

Typed, async-first event bus with wildcard subscriptions (`user.*`, `user.**`), priority-based
dispatch, middleware chain (logging, correlation IDs, retry, deduplication), and pluggable
brokers (in-process, Redis Pub/Sub for cross-process).

**Install (clone from source):**

```bash
git clone https://github.com/damien220/Event-Dispatcher-Tool
cd EEvent-Dispatcher-Tool/dist && pip install event_dispatcher-0.1.0-py3-none-any.whl
```

```python
from event_dispatcher import create_dispatcher, DispatchEvent

dispatcher = create_dispatcher("local")

@dispatcher.subscribe("user.*")
async def on_user_event(event: DispatchEvent) -> None:
    log.info("User event", extra={"kind": event.kind, "payload": event.payload})

await dispatcher.dispatch(DispatchEvent(kind="user.created", payload={"id": "u-1"}))
```

### `job_manager`

Abstract base for background job scheduling: cron, interval, date, and dependency triggers;
thread/process/async executors; persistent job stores; built-in retry and notification listeners.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/Job_Manager
cd Job_Manager/dist && pip install job_manager-0.1.0-py3-none-any.whl
```

```python
from job_manager import (
    BackgroundScheduler, MemoryJobStore, ThreadPoolExecutor,
    BaseJob, IntervalTrigger, JobContext,
)

class CleanupJob(BaseJob):
    def execute(self, context: JobContext) -> str:
        delete_old_records()
        return "done"

scheduler = BackgroundScheduler(MemoryJobStore(), ThreadPoolExecutor(max_workers=2))
scheduler.add_job(CleanupJob(name="cleanup"), IntervalTrigger(seconds=3600))
scheduler.start()
```

### `workflow_manager`

Declarative multi-step workflow engine: `FunctionStep`, `AgentStep`, `ToolStep`, `ParallelStep`,
`DecisionStep`; state machine with checkpoint/resume across restarts; composable middleware.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/Workflow_Manager
cd Workflow_manager/dist && pip install workflow_manager-0.1.0-py3-none-any.whl
```

```python
from workflow_manager import WorkflowEngine, Workflow, FunctionStep

wf = Workflow(name="onboard-user", steps=[
    FunctionStep(name="validate", fn=validate_user),
    FunctionStep(name="create",   fn=create_account),
    FunctionStep(name="notify",   fn=send_welcome_email),
])

engine = WorkflowEngine()
result = await engine.run(wf, context={"user_id": "u-123"})
```
