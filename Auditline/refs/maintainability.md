# Maintainability

Sources: PEP 8 and PEP 257; PEP 484; Google Engineering Practices, *Code Review Developer
Guide* ("Design", "Complexity", "Naming", "Comments"); Hunt and Thomas, *The Pragmatic
Programmer* (DRY); Sandi Metz, "The Wrong Abstraction"; McCabe, "A Complexity Measure" (1976);
Martin, *Clean Code* (names, constants); mypy, TypeScript and import-linter docs; MITRE CWE as
cited per rule.

## Contents

1. How to use this ref
2. Rule map
3. Names, dead code and constants: MAINT-01, MAINT-02, MAINT-03, MAINT-06
4. Structure: MAINT-04, MAINT-05, MAINT-07
5. Types and docs: MAINT-08, MAINT-09
6. Do not flag

## 1. How to use this ref

- **Rule IDs.** `<LANG>-MAINT-NN`; the number is the concept across languages. `PY-MAINT-01` is
  the unused import the P1 sample report uses.
- **Report only a real cost to the next reader or the next change.** Say what that cost is in
  `why`: "a caller reading `get_user` will not expect a row to be created". If you cannot name it,
  it is preference, and preference is silence. Style a formatter or linter fixes is a nit
  (X-SEV-08) and collapses to a count when a tool reports it.
- **The project's conventions decide, not yours.** Flag a deviation from a convention only when
  the project states it (lint config, `CLAUDE.md`, a neighbouring file's consistent pattern).
  A different taste is not a defect.
- **Architecture is mechanical.** Layering and import rules belong in import-linter,
  dependency-cruiser or similar. If the project configures one, defer to its output; if not,
  MAINT-05 applies only to violations visible in the diff.
- **Severity ceiling.** Nothing in this ref is above minor on its own. A maintainability issue
  that causes a wrong result (duplicates that already disagree, a name that led to a bug in the
  diff) is filed as a correctness finding.

## 2. Rule map

| ID | Defect | Languages | Default severity |
|---|---|---|---|
| MAINT-01 | Unused import, variable or parameter | PY, NODE, TS | nit (X-SEV-08) |
| MAINT-02 | Name that misleads | PY, NODE, TS | minor; nit if local |
| MAINT-03 | Dead or unreachable code | PY, NODE, TS | minor; nit if small |
| MAINT-04 | Duplicated rule that will drift | PY, NODE, TS | minor |
| MAINT-05 | Layering leak | PY, NODE, TS | minor |
| MAINT-06 | Magic value | PY, NODE, TS | nit; minor for a business rule |
| MAINT-07 | Over-complex changed function | PY, NODE, TS | minor |
| MAINT-08 | Types erased at a boundary | PY, NODE, TS | minor on a public API |
| MAINT-09 | Comment or docstring contradicts the code | PY, NODE, TS | minor on public docs |

## 3. Names, dead code and constants

### PY-MAINT-01 · NODE-MAINT-01 · TS-MAINT-01 — Unused import, variable or parameter
- **Detect:** X-SEV-08 settles the level. `import json` never used; a variable assigned and never
  read; a function parameter never read (not a callback or override signature).
- **Default severity:** nit. A tool reports it, so collapse to a count when ruff, tsc or ESLint ran
  (`refs/severity-and-output-format.md` §8).
- **Why:** reader cost only; the tool autofixes it.
- WRONG:
  ```python
  import json                                  # never used
  def total(items: list[Item], currency: str) -> Decimal:    # currency never read
      return sum((i.price for i in items), Decimal(0))
  ```
- CORRECT:
  ```python
  def total(items: list[Item]) -> Decimal:
      return sum((i.price for i in items), Decimal(0))
  ```
- **Fix:** `ruff check --fix`; remove the parameter and update the callers.
- **Cite:** PEP 8, "Imports"; ruff docs, `F401`; TypeScript, `noUnusedLocals`.
- **Tool code:** `[ruff: F401, F841, ARG001]`, `[tsc: TS6133]`, `[eslint: no-unused-vars]`.

### PY-MAINT-02 · NODE-MAINT-02 · TS-MAINT-02 — Name that misleads
- **Detect:** the name says one thing and the body does another: `is_valid()` that raises or
  mutates; `get_user()` that creates a row; `validate_email()` that returns a normalised value;
  `users` holding a dict or a single user; a negated flag (`disable_cache=False`, `notFound`); a
  numeric name with no unit where the unit matters (`amount`, `price`, `timeout`: cents or
  dollars, seconds or milliseconds); a function named `handle_*` / `process_*` / `do_*` that does
  five things.
- **Default severity:** minor when the name is public, used at two or more call sites, or hides a
  money or time unit; nit for a local variable. If a call site in the diff is already wrong because
  of the name, file the bug under correctness.
- **Why:** callers trust the name and never read the body.
- WRONG:
  ```python
  def get_customer(email: str) -> Customer:        # creates the customer when missing
      return Customer.objects.get_or_create(email=email)[0]
  def charge(amount: int) -> None: ...             # cents? dollars?
  ```
- CORRECT:
  ```python
  def get_or_create_customer(email: str) -> Customer:
      return Customer.objects.get_or_create(email=email)[0]
  def charge(amount_cents: int) -> None: ...
  ```
- **Fix:** rename (or split) so the name states the effect and the unit; a rename is cheap now and
  costly after merge.
- **Cite:** Google Engineering Practices, "Naming" (a name should say what the thing is or does);
  Martin, *Clean Code* ch. 2 (names); PEP 8, "Naming Conventions"; CWE-1099 (inconsistent naming).
- **Tool code:** none (`[ruff: N8xx]` checks case conventions only).

### PY-MAINT-03 · NODE-MAINT-03 · TS-MAINT-03 — Dead or unreachable code
- **Detect:** statements after `return`, `raise` or `throw`; `if False:` / `if (false)`; a
  condition that is always true or false given the types; a function, class or export added by the
  diff with no reference anywhere (search before claiming); a feature-flag branch whose flag is a
  constant; a dependency added to a manifest and imported nowhere; an `else` after a `return`
  that can never run.
- **Default severity:** minor when it is more than a few lines or sends the reader to the wrong
  branch; nit otherwise. Commented-out code is `X-DIFF-02`.
- **Why:** readers must work out that it never runs, and maintainers keep it compiling.
- WRONG:
  ```ts
  export function formatPrice(cents: number): string {
    return `$${(cents / 100).toFixed(2)}`;
    console.log('formatted', cents);                 // unreachable
  }
  export function legacyFormat(cents: number): string { … }   // added in this diff, no callers
  ```
- CORRECT:
  ```ts
  export function formatPrice(cents: number): string {
    return `$${(cents / 100).toFixed(2)}`;
  }
  ```
- **Fix:** delete it; version control keeps the history.
- **Cite:** CWE-561 (dead code); CWE-570 and CWE-571 (always false, always true); SonarSource
  rule S1763 (unreachable code); TypeScript docs, `allowUnreachableCode`.
- **Tool code:** `[eslint: no-unreachable, no-constant-condition]`, `[tsc: TS7027]`,
  `[mypy: --warn-unreachable]`; unreferenced functions and dependencies are model findings.

### PY-MAINT-06 · NODE-MAINT-06 · TS-MAINT-06 — Magic value
- **Detect:** an unexplained literal inside logic: `if retries > 7`, `time.sleep(86400)`,
  `status == 3`, `price * 1.0825`, `slice(0, 12)`; the same string literal (`"admin"`,
  `"pending"`) compared in several files; a regex or format string with no name.
  Do not flag `0`, `1`, `-1`, `2` for halving or doubling, HTTP status codes, indexes, test data,
  or a literal that already sits in a named constant.
- **Default severity:** nit. Minor when the literal is a business rule (tax rate, limit,
  threshold) or the same value appears three or more times and the copies can drift.
- **Why:** the reader cannot tell what the number means or where else it must change.
- WRONG:
  ```js
  if (user.failedLogins > 5 && Date.now() - user.lastFailed < 900000) lockAccount(user);
  ```
- CORRECT:
  ```js
  const MAX_FAILED_LOGINS = 5;
  const LOCKOUT_WINDOW_MS = 15 * 60 * 1000;
  if (user.failedLogins > MAX_FAILED_LOGINS && Date.now() - user.lastFailed < LOCKOUT_WINDOW_MS) lockAccount(user);
  ```
- **Fix:** named constants (or an enum) with the unit in the name; config for values that change per
  environment.
- **Cite:** Martin, *Clean Code* G25 (replace magic numbers with named constants); CWE-1106
  (insufficient use of symbolic constants); PEP 8, "Constants".
- **Tool code:** `[ruff: PLR2004]`, `[eslint: no-magic-numbers]` (both noisy; confirm that the
  literal is a rule, not a trivial value).

## 4. Structure

### PY-MAINT-04 · NODE-MAINT-04 · TS-MAINT-04 — Duplicated rule that will drift
- **Detect:** one business rule written in two places (a price calculation, a validation, a
  permission check, a status transition, a date format): a block copied with one constant
  changed; a new function that repeats an existing helper's logic (search for the helper); the same
  SQL fragment or regex in several files. Quote both locations.
- **Default severity:** minor. If the copies already disagree in the diff (one has the fix, the
  other does not), it is a correctness finding at the level of that bug.
- **Why:** the next change updates one copy; the other keeps the old behavior.
- WRONG:
  ```python
  # orders/pricing.py
  total = subtotal + (subtotal * Decimal("0.0825"))
  # invoices/render.py (new in the diff)
  total = subtotal + (subtotal * Decimal("0.0825"))     # the tax rule, again
  ```
- CORRECT:
  ```python
  # orders/pricing.py
  def with_tax(subtotal: Decimal) -> Decimal: …
  # invoices/render.py
  total = with_tax(subtotal)
  ```
- **Fix:** call the existing function or extract one; leave similar-looking but unrelated code
  alone. Do not merge incidental duplicates: the wrong abstraction costs more than the copy.
- **Cite:** Hunt and Thomas, *The Pragmatic Programmer* (DRY: every piece of knowledge has a single
  authoritative representation); Metz, "The Wrong Abstraction"; CWE-1041 (use of redundant code).
- **Tool code:** none in the standard set; `[pylint: duplicate-code]` or `jscpd` when the project
  runs them.

### PY-MAINT-05 · NODE-MAINT-05 · TS-MAINT-05 — Layering leak
- **Detect:** only against a layering the project visibly has (directories such as `routes/`,
  `services/`, `repositories/`, `domain/`; an import-linter or dependency-cruiser config). SQL or
  ORM calls inside a route handler or React component; a business rule inside a controller; a
  domain module that imports the web framework (`from flask import request`); `req` / `res`
  passed into service code; a component that fetches, reshapes and renders in one body; reaching
  into another module's private name (`_attr`, `module._helper`); a function-level import added
  to dodge a circular import.
- **Default severity:** minor (C3). Silence when the project has an automated boundary check and it
  passes, or when the project has no visible layering.
- **Why:** logic that lives in the web layer cannot be tested or reused without the framework.
- WRONG:
  ```python
  # domain/pricing.py
  from flask import request
  def discount() -> Decimal:
      return Decimal("0.1") if request.args.get("promo") == "WELCOME" else Decimal(0)   # domain reads HTTP
  ```
- CORRECT:
  ```python
  # domain/pricing.py
  def discount(promo: str | None) -> Decimal:
      return Decimal("0.1") if promo == "WELCOME" else Decimal(0)
  # routes/cart.py
  price = apply(discount(request.args.get("promo")))
  ```
- **Fix:** pass values in, not the request; move the query to the repository or the data hook;
  enforce the boundary with a lint rule rather than a review comment.
- **Cite:** Google Engineering Practices, "Design"; import-linter docs, "Contract types";
  dependency-cruiser docs, "Rules reference"; PEP 8, "Naming Conventions" (a leading underscore
  marks internal use).
- **Tool code:** `[ruff: PLC0415]` (import outside top level); boundary rules need import-linter
  or dependency-cruiser.

### PY-MAINT-07 · NODE-MAINT-07 · TS-MAINT-07 — Over-complex changed function
- **Detect:** a function that the diff adds or makes larger and that now exceeds about 50 lines,
  a cyclomatic complexity of 10, nesting depth of 3, or 5 parameters; a boolean parameter that
  forks the behavior (`process(order, True, False)`); a long `if / elif` chain on a type or
  status that a dispatch table would replace. Do not flag complexity the diff did not add.
- **Default severity:** minor. Nit when a metric is the only evidence and the function reads
  clearly.
- **Why:** each extra branch multiplies the cases a reader and a test must hold.
- WRONG:
  ```python
  def ship(order, express, gift, insured, notify):         # four booleans: 16 call-site meanings
      if express:
          if gift:
              ...
  ```
- CORRECT:
  ```python
  @dataclass(frozen=True)
  class ShipOptions:
      express: bool = False
      gift: bool = False
      insured: bool = False
      notify: bool = True
  def ship(order: Order, options: ShipOptions) -> Shipment: …
  ```
- **Fix:** extract named steps; replace flag arguments with an options object or separate
  functions; use a lookup table for branching on a value.
- **Cite:** McCabe, "A Complexity Measure" (IEEE Trans. Software Eng., 1976); Google Engineering
  Practices, "Complexity"; CWE-1121.
- **Tool code:** `[ruff: C901, PLR0912, PLR0913, PLR0915, FBT001, FBT002]`,
  `[eslint: complexity, max-depth, max-params, max-lines-per-function]`.

## 5. Types and docs

### PY-MAINT-08 · NODE-MAINT-08 · TS-MAINT-08 — Types erased at a boundary
- **Detect:** Python: a public function with no annotations; `Any` in a public signature;
  `# type: ignore` with no error code; `cast(...)` used to silence the checker; `dict[str, Any]`
  passed between layers where a dataclass, `TypedDict` or model would do. TypeScript: `any`,
  `as any`, `as unknown as T`, `@ts-ignore` (prefer `@ts-expect-error` with a description), a
  chain of `!`, and `JSON.parse(text) as Order` or `(await res.json()) as Order` (an assertion, not
  validation: the data is unchecked).
- **Default severity:** minor on an exported or public API and at trust boundaries (C3); nit for
  internal code. Unvalidated external data cast to a type that then drives auth, money or SQL is
  filed under the matching `-SEC-` rule.
- **Why:** the type checker is told to stop looking, so the next change loses its safety net.
- WRONG:
  ```python
  def apply_discount(order, code):                          # public, untyped
      return order.total * RATES[code]  # type: ignore
  ```
  ```ts
  const order = (await res.json()) as Order;                // nothing checks the shape
  ```
- CORRECT:
  ```python
  def apply_discount(order: Order, code: str) -> Decimal:
      return order.total * RATES[code]
  ```
  ```ts
  const order = OrderSchema.parse(await res.json());        // Zod: parsed, then typed
  ```
- **Fix:** annotate the public surface; replace ignores with fixes; parse external data into a
  type at the boundary instead of asserting it.
- **Cite:** PEP 484; mypy docs, "Error codes" (`ignore-without-code`); TypeScript handbook, "Type
  Assertions"; TypeScript 3.9 release notes (`@ts-expect-error`).
- **Tool code:** `[ruff: ANN001, ANN201, ANN401, PGH003]`,
  `[typescript-eslint: no-explicit-any, ban-ts-comment, no-non-null-assertion, no-unsafe-assignment]`.

### PY-MAINT-09 · NODE-MAINT-09 · TS-MAINT-09 — Comment or docstring contradicts the code
- **Detect:** a docstring or JSDoc whose parameters, return value or raised errors no longer match
  the signature or body after the diff ("returns `None` if not found" while the code raises); a
  comment that states a number the constant no longer has ("retry 3 times", `MAX_RETRIES = 5`);
  an OpenAPI or README snippet changed in code but not in the doc that sits beside it.
- **Default severity:** minor when public documentation contradicts behavior callers rely on
  (C3); nit for an inline comment.
- **Why:** readers trust the comment over the code and write callers against it.
- WRONG:
  ```python
  def find_user(email: str) -> User | None:
      """Return the user, or None if no user has this email."""
      return User.objects.get(email=email)          # raises User.DoesNotExist
  ```
- CORRECT:
  ```python
  def find_user(email: str) -> User | None:
      """Return the user, or None if no user has this email."""
      return User.objects.filter(email=email).first()
  ```
- **Fix:** change the code or the comment so they agree; prefer deleting a comment that restates
  the code.
- **Cite:** PEP 257 (docstring conventions); Google Engineering Practices, "Comments"; CWE-1116
  (inaccurate comments).
- **Tool code:** `[ruff: D417]` (documented parameters only), `[eslint: jsdoc/check-param-names]`
  with the jsdoc plugin.

## 6. Do not flag

| Pattern | Why it is not a finding |
|---|---|
| Style a formatter owns: quotes, trailing commas, line length, import order | formatter or linter; a nit count at most |
| Imperative versus functional, `if` versus ternary, class versus function | preference |
| A long file, or a function over the limit that the diff did not touch | not caused by this change |
| "Could use pattern X" or "add an abstraction" with no present cost | speculative |
| A missing docstring on a private or self-explanatory function | no reader cost |
| Duplication in test setup, fixtures or table-driven cases | incidental; tests favour clarity |
| A name that differs from your taste but matches the surrounding code | local convention wins |
| `Any` or `any` in a test double, a generated file or a third-party shim | contained |
| Magic numbers in tests, migrations or one-off scripts | no drift risk |
| A convention the project does not state anywhere | opinion |
