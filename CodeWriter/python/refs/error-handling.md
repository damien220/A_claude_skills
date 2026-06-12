# Error Handling & Exceptions — Python Reference

Grounded in **PEP 8** (exception style), **PEP 3134** (exception chaining), and the `contextlib`
docs. Ruff `E722` (bare except) and `B` (bugbear) enforce several of these.

## Catch the specific exception, never bare `except`

A bare `except:` (or `except Exception:` used carelessly) swallows everything — including
`KeyboardInterrupt`, `SystemExit`, and bugs like `NameError` — and hides the real failure. Catch
the narrowest exception you can actually handle.

```python
# WRONG — hides every error, including typos and Ctrl-C (E722)
try:
    value = config[key]
except:
    value = None
```

```python
# CORRECT — catch only what you expect and can handle
try:
    value = config[key]
except KeyError:
    value = None
```

Catch multiple related types with a tuple; only catch `Exception` at a top-level boundary (a
request handler, a worker loop) where you log and convert it — and re-raise or respond, never
silently continue.

```python
try:
    resp = client.get(url, timeout=10.0)
except (httpx.TimeoutException, httpx.ConnectError) as err:
    raise ServiceUnavailable(url) from err
```

## Never silently swallow

`except ...: pass` discards information that a future debugger will need. If you truly intend to
ignore an error, say so explicitly with `contextlib.suppress` and a comment on _why_.

```python
# WRONG — error vanishes with no trace
try:
    os.remove(path)
except OSError:
    pass
```

```python
# CORRECT — intent is explicit; still scoped to the specific error
from contextlib import suppress

with suppress(FileNotFoundError):     # deleting an already-absent file is fine
    os.remove(path)
```

At minimum, log before continuing: `logger.warning("cleanup failed for %s", path, exc_info=True)`.

## Chain with `raise ... from` to preserve the cause

When you translate a low-level error into a domain error, chain it so the traceback keeps the
original cause (PEP 3134). Use `from None` only to deliberately _hide_ an irrelevant internal cause.

```python
# WRONG — original traceback is lost; debugging starts from zero
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    raise ConfigError("invalid config")
```

```python
# CORRECT — cause chain preserved (“... the above exception was the direct cause ...”)
try:
    data = json.loads(raw)
except json.JSONDecodeError as err:
    raise ConfigError("invalid config") from err
```

## Define a small custom exception hierarchy

Give a library/app one base exception and specific subclasses, so callers can catch at the
granularity they need. Subclass the most specific built-in that fits (`ValueError`, `OSError`).

```python
class PaymentError(Exception):
    """Base for all payment-domain failures."""

class CardDeclined(PaymentError): ...
class GatewayTimeout(PaymentError): ...

# Callers can catch broadly (PaymentError) or narrowly (CardDeclined).
```

## EAFP over LBYL

Pythonic style prefers "easier to ask forgiveness than permission" — try the operation and handle
the exception — over "look before you leap" guards, which race and duplicate checks.

```python
# WRONG (LBYL) — racy (file can vanish between check and open) and verbose
if os.path.exists(path):
    with open(path) as f:
        data = f.read()
else:
    data = ""
```

```python
# CORRECT (EAFP)
try:
    with open(path) as f:
        data = f.read()
except FileNotFoundError:
    data = ""
```

LBYL is fine when the check is cheap, non-racy, and clearer (e.g. validating an argument's range
before work begins).

## Use context managers for cleanup, not `finally` juggling

Anything acquired (files, locks, sockets, DB transactions) should be released by a `with` block,
which runs cleanup even on exception or early return. Reserve `try/finally` for cases without a
context manager, or write your own with `@contextlib.contextmanager`.

```python
# WRONG — leaks the handle if read() raises
f = open(path)
data = f.read()
f.close()
```

```python
# CORRECT
with open(path) as f:                 # closed automatically, even on error
    data = f.read()

# Custom resource:
from contextlib import contextmanager

@contextmanager
def acquired(lock):
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()
```

## Don't use exceptions for ordinary control flow

Exceptions signal the _exceptional_. Returning a value, an `Optional`, or a small result object is
clearer for expected outcomes (e.g. "not found" in a lookup that's often empty). Validate inputs at
the boundary and raise there, so the core logic can assume well-formed data.

## Dev_util_prj — `error_exception_handler`

`Error-Exception_Handler` provides a ready-made base exception class with machine-readable codes,
HTTP status codes, metadata, and cause chaining — plus a central `ErrorHandler` that normalises
any exception into a consistent structured response across HTTP, CLI, and logs.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/Error_Exception_Handler
cd Error-Exception_Handler/dist && pip install error_exception_handler-0.1.0-py3-none-any.whl
```

```python
from error_handler import AppBaseException, ValidationException, ErrorHandler

class PaymentError(AppBaseException): ...
class CardDeclined(PaymentError): ...

raise ValidationException("Email is required", details={"field": "email"})

# At the boundary (request handler, worker loop):
result = ErrorHandler.handle(exc)
# → {"status_code": 400, "body": {"success": False, "error": {"code": "VALIDATION_ERROR", ...}}}
```
