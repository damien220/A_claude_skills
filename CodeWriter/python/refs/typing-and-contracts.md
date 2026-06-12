# Type Hints & Contracts — Python Reference

Grounded in **PEP 484** (type hints), **PEP 585** (builtin generics), **PEP 604** (`X | Y`),
**PEP 612** (`ParamSpec`), **PEP 613/695** (type aliases), and the mypy docs. Types are the
machine-checked contract — `tooling/mypy.ini` enforces them.

## Annotate every public function fully

`disallow_untyped_defs` means parameters *and* return type. `-> None` is explicit, not optional.

```python
# WRONG — untyped; mypy flags, and the contract is invisible
def fetch(url, retries=3):
    ...
```

```python
# CORRECT
def fetch(url: str, retries: int = 3) -> bytes:
    ...
```

## Modern syntax (ruff `UP` upgrades these automatically)

| Old | Modern (3.10+) |
|---|---|
| `List[int]`, `Dict[str, int]` | `list[int]`, `dict[str, int]` |
| `Optional[int]` | `int \| None` |
| `Union[int, str]` | `int \| str` |
| `Tuple[int, ...]` | `tuple[int, ...]` |

```python
# WRONG                                   # CORRECT
from typing import List, Optional, Dict   def parse(raw: str) -> dict[str, int] | None:
def parse(raw: str) -> Optional[Dict[str, int]]:        ...
```

If you must support <3.10 at runtime, add `from __future__ import annotations` so the new syntax
is accepted as strings.

## `Optional` and implicit-None

`no_implicit_optional` forbids a `None` default on a non-optional type. Make optionality explicit.

```python
# WRONG                                   # CORRECT
def greet(name: str = None):              def greet(name: str | None = None) -> str:
    ...                                       return f"hi {name or 'there'}"
```

Narrow `None` before use so mypy proves safety:

```python
def head(items: list[str] | None) -> str:
    if items is None or not items:
        raise ValueError("empty")
    return items[0]            # mypy knows items is list[str] here
```

## `Final`, `Literal`, and constants

- `Literal[...]` restricts a value to a fixed set — far more precise than `str`.
- `Final` marks a name that must not be reassigned.

```python
from typing import Final, Literal

MAX_RETRIES: Final = 3
Mode = Literal["r", "w", "a"]

def open_file(path: str, mode: Mode = "r") -> None:
    ...

open_file("x", "rw")          # mypy error: "rw" is not a valid Mode
```

## Generics and `TypeVar` — for reusable containers, not one-offs

Use generics when a function/class is genuinely parametric over a type it preserves. Don't reach
for them in ordinary application code.

```python
# WRONG — Any throws away the relationship between input and output
def first(items: list) -> object:
    return items[0]
```

```python
# CORRECT — the element type flows through
from collections.abc import Sequence

def first[T](items: Sequence[T]) -> T:    # PEP 695 syntax (3.12+)
    return items[0]

# Pre-3.12 equivalent:
from typing import TypeVar
T = TypeVar("T")
def first_legacy(items: Sequence[T]) -> T:
    return items[0]
```

Use `collections.abc` types (`Sequence`, `Mapping`, `Iterable`) in **parameters** to accept the
widest input, and concrete types (`list`, `dict`) in **returns** so callers know what they get.

```python
from collections.abc import Iterable

def total(values: Iterable[int]) -> int:   # accepts list, tuple, generator, set…
    return sum(values)
```

## Don't let `Any` leak

`warn_return_any` flags functions that return `Any`. `Any` disables checking — quarantine it at
the boundary (e.g. right after `json.loads`) and convert to a typed shape immediately.

```python
# WRONG — Any propagates through the whole call graph
def load(raw: str):
    return json.loads(raw)        # -> Any, infects every caller
```

```python
# CORRECT — validate/cast at the boundary into a typed shape
import json
from typing import TypedDict, cast

class Config(TypedDict):
    host: str
    port: int

def load(raw: str) -> Config:
    data = json.loads(raw)
    if not isinstance(data, dict) or "host" not in data:
        raise ValueError("bad config")
    return cast(Config, data)     # or validate with Pydantic for untrusted input
```

## Typing callables and decorators

Use `collections.abc.Callable` for simple callbacks and `ParamSpec` to preserve a wrapped
function's signature in a decorator.

```python
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

def timed(fn: Callable[P, R]) -> Callable[P, R]:
    @wraps(fn)
    def inner(*args: P.args, **kwargs: P.kwargs) -> R:
        return fn(*args, **kwargs)
    return inner
```

## Python version matrix — match syntax to `requires-python`

**Default to the project's minimum Python version.** Check `pyproject.toml`
`requires-python` before using any feature below. `ruff.toml` `target-version` is the
enforcement gate (ruff `UP` will not suggest syntax newer than the target).

| Version | Key typing / language additions |
|---|---|
| **3.10** | `X \| Y` union syntax (PEP 604); `match`/`case` (PEP 634); `ParamSpec` (PEP 612); `TypeGuard` (PEP 647); `slots=True` on `@dataclass` |
| **3.11** | `Self` type (PEP 673); `LiteralString` (PEP 675); `Required`/`NotRequired` in `TypedDict` (PEP 655); `TaskGroup` / exception groups (PEP 654); `asyncio.timeout()`; `tomllib` stdlib; `StrEnum` |
| **3.12** | `type` alias statement: `type Vector = list[float]` (PEP 695); `[T]` generic syntax in functions/classes (PEP 695); `@override` (PEP 698); `itertools.batched` |
| **3.13** | `@warnings.deprecated` (PEP 702); free-threaded mode (`--disable-gil`, experimental); `typing.ReadOnly` for `TypedDict` fields (PEP 705) |

```python
# WRONG — emitting 3.12 generic syntax in a project with requires-python = ">=3.10"
def first[T](items: list[T]) -> T:   # SyntaxError on 3.10/3.11
    return items[0]
```

```python
# CORRECT — check pyproject.toml requires-python first
# If requires-python = ">=3.12": use PEP 695 syntax
def first[T](items: list[T]) -> T:
    return items[0]

# If requires-python = ">=3.10": use TypeVar
from typing import TypeVar
T = TypeVar("T")
def first(items: list[T]) -> T:
    return items[0]

# If requires-python = "<3.10": add from __future__ import annotations for X | Y unions
from __future__ import annotations
```

### Quick decision: which `X | Y` form to use

| Scenario | Form |
|---|---|
| Project `requires-python >= "3.10"` | `int \| None` directly |
| `requires-python >= "3.7"`, type hints only evaluated at check time | `from __future__ import annotations` at top of file, then `int \| None` |
| `requires-python < "3.7"` | `Optional[int]`, `Union[int, str]` from `typing` |

### `type` aliases (3.12+) vs `TypeAlias` (3.10+)

```python
# 3.10–3.11: TypeAlias makes the intent explicit
from typing import TypeAlias
Vector: TypeAlias = list[float]

# 3.12+: dedicated `type` statement; creates a proper TypeAliasType
type Vector = list[float]          # cleaner; no TypeAlias import needed
```
