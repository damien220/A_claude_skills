# Data Modeling: Classes, Dataclasses & Structs — Python Reference

Grounded in **PEP 557** (dataclasses), **PEP 589** (TypedDict), `typing.NamedTuple`, and the
`dataclasses` / `enum` stdlib docs. Core principle: pick the _lightest_ construct that models the
data honestly.

## Does this even need a class?

A class earns its keep when it bundles **state with behavior that operates on that state**. If a
"class" is just a namespace of static methods, or holds data with no behavior, it is the wrong
tool.

```python
# WRONG — a class used as a namespace for stateless functions
class MathUtils:
    @staticmethod
    def add(a, b): return a + b
    @staticmethod
    def scale(xs, k): return [x * k for x in xs]
```

```python
# CORRECT — module-level functions; the module *is* the namespace
def add(a: float, b: float) -> float:
    return a + b

def scale(xs: list[float], k: float) -> list[float]:
    return [x * k for x in xs]
```

```python
# WRONG — hand-written boilerplate for a pure data record
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    def __repr__(self):
        return f"Point({self.x}, {self.y})"
    def __eq__(self, other):
        return (self.x, self.y) == (other.x, other.y)
```

```python
# CORRECT — @dataclass generates __init__/__repr__/__eq__
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float
```

## Choosing the record type

| Construct                             | Mutable?               | Use when                                                                          | Notable cost              |
| ------------------------------------- | ---------------------- | --------------------------------------------------------------------------------- | ------------------------- |
| `@dataclass`                          | yes (or `frozen=True`) | general records with behavior; want defaults, `__post_init__`, methods            | runtime objects           |
| `@dataclass(frozen=True, slots=True)` | no                     | value objects, dict/set keys, memory-sensitive                                    | can't add attrs           |
| `NamedTuple`                          | no                     | tiny immutable record that should also behave like a tuple (unpacking, indexing)  | tuple semantics leak      |
| `TypedDict`                           | yes                    | typing an existing **dict** shape (JSON, kwargs) without changing it to an object | no runtime validation     |
| Pydantic `BaseModel`                  | yes                    | untrusted external data needing **validation/coercion** (API bodies, config)      | third-party dep, overhead |
| `Enum`                                | n/a                    | a closed set of named constants                                                   | —                         |

Decision order: plain `@dataclass` by default → add `frozen=True, slots=True` for value objects →
`TypedDict` when the data is and must stay a dict → Pydantic only when you need validation at a
trust boundary → `NamedTuple` only when tuple-ness is genuinely wanted.

```python
# TypedDict: describe a JSON shape without converting it to an object
from typing import TypedDict

class WebhookPayload(TypedDict):
    id: str
    amount: int
    currency: str

def total_cents(p: WebhookPayload) -> int:
    return p["amount"]            # mypy knows the keys and their types
```

```python
# Pydantic: validate/coerce data crossing a trust boundary
from pydantic import BaseModel, field_validator

class CheckoutRequest(BaseModel):
    amount: int
    currency: str

    @field_validator("amount")
    @classmethod
    def positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be positive")
        return v
```

## `frozen` and `slots`

- `frozen=True` makes instances immutable (hashable, safe as dict/set keys, no accidental mutation).
- `slots=True` (Python 3.10+ dataclasses) drops the per-instance `__dict__`, cutting memory and
  speeding attribute access — valuable when you create many instances. Trade-off: no dynamic
  attributes, and multiple inheritance with slots needs care.

```python
@dataclass(frozen=True, slots=True)
class Money:
    amount: int          # store cents as int; never float for currency
    currency: str
```

## Mutable default arguments — never

A mutable default is created **once** and shared across all calls (ruff `B006`). Use `None` +
`field(default_factory=...)`.

```python
# WRONG — the same list is shared by every instance/call
def add_tag(tag, tags=[]):       # B006
    tags.append(tag)
    return tags

@dataclass
class Cart:
    items: list[str] = []        # error: mutable default in dataclass
```

```python
# CORRECT
from dataclasses import dataclass, field

def add_tag(tag: str, tags: list[str] | None = None) -> list[str]:
    tags = [] if tags is None else tags
    tags.append(tag)
    return tags

@dataclass
class Cart:
    items: list[str] = field(default_factory=list)
```

## `__slots__` for plain classes

If a non-dataclass class is instantiated in large numbers, declare `__slots__` to remove the
`__dict__` overhead.

```python
class Pixel:
    __slots__ = ("r", "g", "b")
    def __init__(self, r: int, g: int, b: int) -> None:
        self.r, self.g, self.b = r, g, b
```

## Enums — closed sets of named constants

**Grounded in PEP 435** (enum), Python 3.11 `StrEnum` docs, and the `enum` stdlib docs.

Use an `Enum` (or one of its typed subclasses) for any closed set of named constants that has
identity or behavior. Do not use bare strings or ints scattered through the codebase.

### Which subclass to use

| Subclass           | Values are           | Use when                                                                      | Caution                             |
| ------------------ | -------------------- | ----------------------------------------------------------------------------- | ----------------------------------- |
| `Enum`             | anything             | general case; values don't need to be ints or strings                         | members don't format as their value |
| `StrEnum` (3.11+)  | `str`                | status fields, serialization keys, anywhere `isinstance(v, str)` must be true | —                                   |
| `IntEnum`          | `int`                | interop with legacy code or C APIs expecting real ints                        | less type-safe; avoid in new code   |
| `Flag` / `IntFlag` | combinable bit flags | permissions, feature flags                                                    | use `auto()` for values             |

```python
# WRONG — bare strings; typos are silent, no completion, no type narrowing
STATUS_ACTIVE = "active"
STATUS_BANNED = "banned"

def can_login(status: str) -> bool:
    return status == "actve"   # silent typo; tests may not catch it
```

```python
# CORRECT — StrEnum: members ARE strings, no .value needed at boundaries
from enum import StrEnum, auto

class UserStatus(StrEnum):
    ACTIVE = auto()    # value = "active" (lowercased name)
    BANNED = auto()
    PENDING = auto()

def can_login(status: UserStatus) -> bool:
    return status == UserStatus.ACTIVE

# Serialises cleanly: json.dumps({"status": UserStatus.ACTIVE}) → '{"status": "active"}'
# isinstance check: isinstance(UserStatus.ACTIVE, str) → True
```

```python
# Flag: combinable permission bits
from enum import Flag, auto

class Permission(Flag):
    READ  = auto()
    WRITE = auto()
    ADMIN = auto()
    EDITOR = READ | WRITE   # combination is a valid member

user_perms = Permission.READ | Permission.WRITE
if Permission.WRITE in user_perms:
    save(document)
```

### `auto()` — let the enum assign values

`auto()` generates unique values automatically so you never manually number enum members. For
plain `Enum` and `Flag`, `auto()` returns incrementing integers starting at 1. For `StrEnum`,
`auto()` returns the lowercased member name.

```python
from enum import Enum, auto

class Color(Enum):
    RED   = auto()   # 1
    GREEN = auto()   # 2
    BLUE  = auto()   # 3
```

### Enum vs `Literal` — when to use each

|                       | `Enum`                                                                   | `Literal["a", "b"]`                                                                             |
| --------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| Runtime identity      | yes — `status is UserStatus.ACTIVE`                                      | no — it's still a plain string at runtime                                                       |
| Shared across modules | yes — import the Enum class                                              | awkward — must repeat the Literal everywhere                                                    |
| Behavior / methods    | yes — add methods to the class                                           | no                                                                                              |
| Serialization         | `.value` needed for plain `Enum`; `StrEnum` is transparent               | no extra step                                                                                   |
| Use when              | the constant has identity, is used in multiple modules, or needs methods | typing-only constraint on a string/int accepted from outside (e.g. a narrow function parameter) |

```python
# Literal: a narrow function parameter; no shared identity needed
from typing import Literal

def open_file(path: str, mode: Literal["r", "w", "a"] = "r") -> None:
    ...
```

### Formatting gotcha: plain `Enum` members don't format as their value

```python
class Color(Enum):
    RED = "red"

f"color={Color.RED}"          # "color=Color.RED"  ← probably not what you want
f"color={Color.RED.value}"    # "color=red"        ← explicit .value
f"color={Color.RED!s}"        # "color=Color.RED"  ← still the name

# Use StrEnum to avoid this entirely:
class Color(StrEnum):
    RED = auto()              # value = "red"
f"color={Color.RED}"          # "color=red"        ← formats as the string value
```

## Dev_util_prj — `inout_models`

`inout_models` provides a shared Pydantic v2 foundation: `AbstractBaseModel` with
`to_dict/to_json/from_dict/from_json` built in, a typed field catalog (`Email`, `UUIDField`,
`Timestamp`, `NonEmptyStr`), and `ValidationException` with structured `details.fields`.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/InOut_Models
cd InOut_Models/Dependencies && pip install inout_models-0.1.0-py3-none-any.whl
```

```python
from inout_models import AbstractBaseModel, ValidationException
from inout_models.fields import Email, UUIDField, Timestamp

class UserCreateRequest(AbstractBaseModel):
    id: UUIDField
    email: Email
    created_at: Timestamp

user = UserCreateRequest.from_dict({
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "ADA@EXAMPLE.COM",        # normalised → ada@example.com
    "created_at": "2026-01-01T00:00:00Z",
})
user.to_json()  # → serialized JSON string
```
