# Abstraction, Interfaces & Polymorphism — Python Reference

Grounded in **PEP 544** (Protocols / structural subtyping), the `abc` and `typing` docs, and the
community "composition over inheritance" consensus.

## Protocol vs ABC

|               | `typing.Protocol`                                                            | `abc.ABC`                                                        |
| ------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Subtyping     | structural — any class with the right methods matches, no inheritance needed | nominal — a class must explicitly subclass                       |
| Coupling      | zero; the implementer need not know the Protocol exists                      | tight; implementer imports and inherits the base                 |
| Best for      | defining what a _consumer_ needs ("anything with `.read()`")                 | sharing implementation, or enforcing a contract at instantiation |
| Runtime check | only with `@runtime_checkable`, and only method _presence_                   | `isinstance` works; abstract methods block instantiation         |

**Default to `Protocol`** for interfaces — it keeps implementations decoupled and matches Python's
duck typing. Use `ABC` when subclasses should inherit shared code, or when you must fail loudly at
construction time if a method is missing.

```python
# WRONG — forcing inheritance just to express "needs a write method"
from abc import ABC, abstractmethod

class Sink(ABC):
    @abstractmethod
    def write(self, data: bytes) -> None: ...

class S3Sink(Sink):           # every sink must import and subclass Sink
    def write(self, data): ...
```

```python
# CORRECT — Protocol: the consumer declares the shape; implementers stay independent
from typing import Protocol

class Sink(Protocol):
    def write(self, data: bytes) -> None: ...

def export(rows: list[bytes], sink: Sink) -> None:   # accepts ANY object with write(bytes)
    for row in rows:
        sink.write(row)

class S3Sink:                  # no base class, no import of Sink — still matches structurally
    def write(self, data: bytes) -> None: ...
```

Use `ABC` when there is real shared behavior:

```python
from abc import ABC, abstractmethod

class Retryer(ABC):
    def run(self, fn):                 # shared implementation
        for attempt in range(self.max_attempts()):
            try:
                return fn()
            except Exception:          # illustrative; see error-handling ref
                if attempt + 1 == self.max_attempts():
                    raise

    @abstractmethod
    def max_attempts(self) -> int: ...
```

## `@runtime_checkable` — and its limits

Add `@runtime_checkable` only when you genuinely need `isinstance(obj, Proto)`. It checks method
**presence**, not signatures or return types — so it can give false positives. Prefer static typing.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Closable(Protocol):
    def close(self) -> None: ...

if isinstance(resource, Closable):     # True for anything with a `close` attr — even a non-method
    resource.close()
```

## Composition over inheritance

Deep hierarchies are rigid and entangle unrelated concerns. Prefer composing small objects and
injecting collaborators. Inheritance is for genuine _is-a_ with shared behavior; "needs-a" is
composition.

```python
# WRONG — behavior bolted on via inheritance; a "LoggingRetryingCachingClient" explosion looms
class HttpClient: ...
class LoggingHttpClient(HttpClient): ...
class RetryingLoggingHttpClient(LoggingHttpClient): ...
```

```python
# CORRECT — compose independent collaborators
class HttpClient:
    def __init__(self, transport: Sink, logger: Logger, retryer: Retryer) -> None:
        self._transport = transport
        self._logger = logger
        self._retryer = retryer
```

## Replace `isinstance` ladders with polymorphism or dispatch

A chain of `isinstance` checks reimplements method dispatch by hand and must be edited every time
a type is added. Prefer a polymorphic method on each type, or `functools.singledispatch`.

```python
# WRONG — type-dispatch ladder; adding a shape edits this function
def area(shape):
    if isinstance(shape, Circle):
        return 3.14159 * shape.r ** 2
    elif isinstance(shape, Square):
        return shape.side ** 2
    raise TypeError(shape)
```

```python
# CORRECT (polymorphism) — each type owns its behavior
from typing import Protocol

class Shape(Protocol):
    def area(self) -> float: ...

@dataclass(frozen=True)
class Circle:
    r: float
    def area(self) -> float:
        return 3.14159 * self.r ** 2

@dataclass(frozen=True)
class Square:
    side: float
    def area(self) -> float:
        return self.side ** 2

def total_area(shapes: list[Shape]) -> float:
    return sum(s.area() for s in shapes)
```

```python
# CORRECT (singledispatch) — when you can't add a method (3rd-party/builtin types)
from functools import singledispatch

@singledispatch
def to_json(value: object) -> str:
    raise TypeError(f"unsupported: {type(value).__name__}")

@to_json.register
def _(value: int) -> str:
    return str(value)

@to_json.register
def _(value: list) -> str:
    return "[" + ", ".join(to_json(v) for v in value) + "]"
```

## Structural pattern matching (`match`/`case`) — Python 3.10+

**Grounded in PEP 634** (structural pattern matching) and **PEP 636** (tutorial).

`match` is the idiomatic 3.10+ answer when you need to branch on the _shape_ of a value —
especially when destructuring fields at the same time. It replaces `isinstance` ladders that
inspect multiple attributes and is more readable than chained `elif`.

```python
# WRONG — isinstance ladder; verbose, must be updated for every new shape
def describe(shape):
    if isinstance(shape, Circle) and shape.r > 0:
        return f"circle r={shape.r}"
    elif isinstance(shape, Square):
        return f"square side={shape.side}"
    else:
        raise ValueError(shape)
```

```python
# CORRECT — match destructures and guards in one expression (Python 3.10+)
from dataclasses import dataclass

@dataclass
class Circle:
    r: float

@dataclass
class Square:
    side: float

def describe(shape: Circle | Square) -> str:
    match shape:
        case Circle(r=r) if r > 0:
            return f"circle r={r}"
        case Square(side=side):
            return f"square side={side}"
        case _:
            raise ValueError(f"unknown shape: {shape!r}")
```

### Pattern kinds — summary

| Pattern  | Syntax                                | Matches                         |
| -------- | ------------------------------------- | ------------------------------- |
| Class    | `case Circle(r=r):`                   | instance of `Circle`; binds `r` |
| Guard    | `case Circle(r=r) if r > 0:`          | class match + condition         |
| Sequence | `case [first, *rest]:`                | any sequence; binds head/tail   |
| Mapping  | `case {"status": 200, "body": body}:` | dict with at least those keys   |
| OR       | `case 400 \| 404 \| 422:`             | any of the listed literals      |
| Wildcard | `case _:`                             | always matches; no binding      |

```python
# Mapping pattern — clean alternative to deeply nested dict lookups
def handle_response(resp: dict) -> str:
    match resp:
        case {"status": 200, "body": {"id": order_id}}:
            return f"order {order_id} confirmed"
        case {"status": 400, "error": msg}:
            raise ValueError(msg)
        case {"status": status} if status >= 500:
            raise RuntimeError(f"server error {status}")
        case _:
            raise RuntimeError(f"unexpected response: {resp!r}")
```

### When to use `match` vs the other tools

| Tool                      | Use when                                                                          |
| ------------------------- | --------------------------------------------------------------------------------- |
| `match`                   | Branching on _shape_ + destructuring fields; multi-field conditions; Python 3.10+ |
| Polymorphic method        | Behavior _owned by the type_ and type is yours to modify                          |
| `singledispatch`          | Dispatch on a single type you don't own or can't modify                           |
| `Protocol` + polymorphism | Long-lived dispatch across many call sites; open for extension                    |

Avoid `match` for single-field enum dispatch — a `dict`-lookup or polymorphic method is cleaner.
Avoid `match` as a replacement for `Protocol`-based polymorphism in library code — it's closed to
extension without editing the `match` block.

## Dev_util_prj — abstract base classes and adapters

### `abstract_agent`

Reusable base class for AI agents. Lifecycle, logging, error normalisation, memory, and LLM caching
are provided via opt-in mixins — concrete agents only implement `process()` and `respond()`.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/Abstract_agent
cd Abstract_agent/dist && pip install abstract_agent-0.5.0-py3-none-any.whl
```

```python
from abstract_agent import AbstractAgent

class MyAgent(AbstractAgent):
    async def process(self, message: str) -> str: ...
    async def respond(self, result: str) -> str: ...
```

### `plugin_loader`

Dynamic plugin loading, registration, and lifecycle management. Supports class-based (ABC),
Protocol/duck-typed, and decorator-based authoring with directory, entry-point, and package discovery.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/Plugin-Loader
cd Plugin_Loader/dist && pip install plugin_loader-0.1.0-py3-none-any.whl
```

```python
from plugin_loader import PluginRegistry

registry = PluginRegistry()
registry.discover("myapp/plugins/")
plugin = registry.get("my-plugin")
```

### `tool_interface_adapter`

Wraps third-party APIs, ML models, and CLI tools behind `AbstractTool` with validated I/O,
retry/cache/logging middleware, and composable `ToolChain`/`ToolGroup`/`Pipeline` patterns.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/Tool_Interface_adapter
cd Tool_Interface_adapter/Dependencies && pip install tool_interface_adapter-0.1.0-py3-none-any.whl
```

```python
from tool_interface_adapter import AbstractTool, ToolSpec, ToolResult

class MyAPITool(AbstractTool):
    spec = ToolSpec(name="my-api", description="Calls My API")
    async def _execute(self, input: dict) -> ToolResult: ...
```

### `notification_manager`

Plugin-based notification dispatch across any delivery channel (Slack, email, SMS, Discord, …).
Channels are runtime plugins; application code only calls `manager.send(notification)`.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/Notification-and-Messaging-Manager
cd Notification_manager/dist && pip install notification_manager-0.1.0-py3-none-any.whl
```

```python
from notification_manager import NotificationManager, Notification, Priority

manager = NotificationManager()
manager.register_plugin(SlackPlugin(webhook_url=os.environ["SLACK_WEBHOOK"]))
await manager.send(Notification(title="Deploy done", priority=Priority.NORMAL))
```

### `ui_controller_base`

Abstract controller layer that decouples business logic from UI surface (Streamlit, FastAPI, CLI).
Thin adapters translate each framework's primitives; the same controller powers every surface.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/UI_controlBase
cd UI_controlBase/Dependencies && pip install ui_controller_base-0.1.0-py3-none-any.whl
```

```python
from ui_controller_base import AbstractUIController

class MyController(AbstractUIController):
    def handle_action(self, action: str, payload: dict) -> dict: ...
```
