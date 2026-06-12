# Naming & Module Layout — Python Reference

Grounded in **PEP 8** (naming conventions, imports), **PEP 3131** (identifier characters), and
isort / ruff rule set `I`. Naming is the central, always-enforced requirement (ruff `N`).

## Identifier case by kind

| Kind | Convention | Example |
|---|---|---|
| Variable, function, method, module, package | `snake_case` | `retry_count`, `parse_header`, `http_client` |
| Class, exception, type alias, `TypeVar` | `PascalCase` | `HttpClient`, `TimeoutError`, `UserId`, `T` |
| Module-level constant | `UPPER_CASE` | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Non-public (internal) name | leading `_` | `_cache`, `_compute_digest` |
| Name-mangled (subclass-private) | leading `__` | `__state` |
| "Avoid shadowing a builtin" trailing `_` | trailing `_` | `class_`, `id_` |

```python
# WRONG — camelCase functions/vars, lowercase class, untyped constant scattered in code
class httpClient:                       # N801: class should be PascalCase
    def parseHeader(self, rawText):     # N802/N803: function + arg should be snake_case
        maxRetries = 3                  # not a constant convention, and magic number inline
        return rawText.split(":")
```

```python
# CORRECT
MAX_RETRIES = 3                         # module-level constant, UPPER_CASE

class HttpClient:                       # PascalCase
    def parse_header(self, raw_text: str) -> tuple[str, str]:  # snake_case, typed
        key, _, value = raw_text.partition(":")
        return key.strip(), value.strip()
```

## Names describe meaning, not type or implementation

A name should let a reader predict the value without scrolling. Avoid Hungarian prefixes
(`str_name`), single letters outside short loops, and vague nouns (`data`, `info`, `tmp`).

```python
# WRONG
d = {}                      # what is in it?
def proc(l):                # `l` reads as 1 or I; "proc" of what?
    for x in l: d[x] = proc2(x)
```

```python
# CORRECT
prices_by_sku: dict[str, Decimal] = {}
def normalize_skus(raw_skus: list[str]) -> list[str]:
    return [sku.strip().upper() for sku in raw_skus]
```

Short names are fine where scope is tiny and idiomatic: `for i in range(n)`, `with open(p) as f`,
comprehension binders, math (`x`, `y`). The rule scales with scope — wider scope, fuller name.

## Booleans and functions read as claims/verbs

Boolean names read as predicates (`is_active`, `has_items`, `should_retry`); functions with side
effects read as verbs (`send_email`, `flush`); pure mappings read as nouns or `to_*`/`as_*`.

```python
# WRONG                              # CORRECT
active = check(user)                 is_active = user.is_active
def email(user): ...                 def send_email(user: User) -> None: ...
```

## Import ordering and form (ruff `I` / isort)

Three groups, blank-line separated, alphabetized within each: **standard library → third-party →
first-party (this project)**. Prefer absolute imports; use explicit relative (`from . import x`)
only within a package. Never `from module import *`.

```python
# WRONG — mixed groups, star import, unordered
from .models import User
import os, sys                        # E401: one import per line
from requests import *               # F403: star import hides names
import json
```

```python
# CORRECT
import json
import os
import sys

import httpx

from myapp.models import User
```

Module-level `__all__` declares the public surface explicitly when a module is imported with `*`
by consumers, and documents intent regardless.

## Module and package naming

Modules/packages are short, all-lowercase, `snake_case` (PEP 8 prefers no underscores for
packages when readable, e.g. `httpclient`, but `snake_case` is acceptable and clearer for
multi-word). Avoid a catch-all `utils.py` / `helpers.py` — name modules for the domain concept
they own (`retry.py`, `serialization.py`). One cohesive responsibility per module.

## Constants and magic values

Replace inline literals that carry meaning with `UPPER_CASE` constants near the top of the module
(or an `Enum` for a closed set). Numbers/strings that appear once and are self-evident (`0`, `""`)
need no constant.

```python
# WRONG                                      # CORRECT
if status == 429:                            TOO_MANY_REQUESTS = 429
    time.sleep(5)                            BACKOFF_SECONDS = 5
                                             if status == TOO_MANY_REQUESTS:
                                                 time.sleep(BACKOFF_SECONDS)
```
