# Documentation & Comments — Python Reference

Grounded in **PEP 257** (docstring conventions) and the Google / NumPy docstring styles. Principle:
type hints carry the *what*; comments and docstrings carry the *why* and the *contract*.

## Docstrings for public modules, classes, and functions

Every public function, class, and module gets a docstring (PEP 257): a one-line summary in the
imperative mood, then — if needed — a blank line and a fuller description plus structured sections.
Private helpers (`_name`) need a docstring only when their logic isn't self-evident.

```python
# WRONG — no docstring; the contract (raises? units? return shape?) is invisible
def withdraw(account, amount):
    if amount > account.balance:
        raise InsufficientFunds
    account.balance -= amount
```

```python
# CORRECT — Google-style docstring documents the contract, not the implementation
def withdraw(account: Account, amount: int) -> None:
    """Deduct `amount` cents from `account`.

    Args:
        account: The account to debit; mutated in place.
        amount: Amount in cents; must be positive.

    Raises:
        InsufficientFunds: If `amount` exceeds the current balance.
    """
    if amount > account.balance:
        raise InsufficientFunds(account.id)
    account.balance -= amount
```

Pick one style (Google or NumPy) and keep it consistent across the codebase. Don't restate types
that are already in the signature — document meaning, units, side effects, and exceptions.

## Comments explain *why*, not *what*

The code already says what it does. A comment earns its place by explaining intent, a non-obvious
constraint, a workaround, or a reference — anything a reader can't recover from the code itself.

```python
# WRONG — narrates the obvious; rots when the code changes
i = i + 1                      # increment i by 1
# loop over users
for user in users:
    ...
```

```python
# CORRECT — explains the non-obvious WHY
# Stripe rate-limits to 100 req/s; batch of 90 leaves headroom for retries.
BATCH_SIZE = 90

# Sort descending so the partial-refund path consumes the largest charges first
# (minimizes the number of charge objects touched — see PAY-412).
charges.sort(key=lambda c: c.amount, reverse=True)
```

A comment that merely repeats the code is worse than none — it adds maintenance cost and drifts out
of sync. If code needs a "what" comment to be understood, prefer renaming or extracting a
well-named function instead.

## Let names and types replace comments

Self-documenting code beats a comment. Replace an explanatory comment with a descriptive name or an
intermediate variable wherever you can.

```python
# WRONG                                          # CORRECT
# check if the subscription is in a grace period  is_in_grace_period = (
if t < s.end + 3 * 86400 and s.status == "past_due":   now < sub.ends_at + GRACE_PERIOD
    ...                                              and sub.status == "past_due"
                                                 )
                                                 if is_in_grace_period:
                                                     ...
```

## Module docstrings and `TODO`s

Start a module with a one-line docstring describing its responsibility. Tag deferred work with a
searchable, attributed marker so it isn't lost:

```python
"""HTTP retry policy: classifies transient failures and applies capped backoff."""

# TODO(dana): replace hand-rolled backoff with tenacity once PAY-501 lands.
```

## Keep docs next to code and true

Documentation that lives far from the code it describes drifts. Prefer docstrings (checked by tools,
shown in IDEs/`help()`) over external prose for API contracts. When you change a function's
behavior, update its docstring in the same edit — a stale docstring actively misleads.
