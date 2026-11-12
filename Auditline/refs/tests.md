# Tests

Sources: pytest docs ("How to parametrize", "How to monkeypatch", "Skip and xfail", `tmp_path`);
Python docs (`unittest.mock`, hash randomization); Jest and Vitest docs; Testing Library docs
("Guiding Principles", "About Queries") and user-event docs; Google Testing Blog; Martin Fowler,
"Mocks Aren't Stubs" and "Eradicating Non-Determinism in Tests"; ISTQB Foundation syllabus
(boundary value analysis).

## Contents

1. How to use this ref
2. Rule map
3. Coverage of the change: TEST-01, TEST-07
4. Assertion quality: TEST-02, TEST-03, TEST-04
5. Reliability: TEST-05, TEST-06, TEST-08
6. Frontend tests: TEST-09
7. Do not flag

## 1. How to use this ref

- **Rule IDs.** `<LANG>-TEST-NN`; the number is the concept across languages.
- **Search before claiming a gap.** For TEST-01, grep the repository's test directories for the
  function, route or module name before saying it is untested. A test in a file the diff does not
  touch is the usual case; if you did not search, the confidence is low (a question, not a finding).
- **The question for every test:** would it fail if the change were reverted or the logic broken?
  If not, it protects nothing. Say which mutation it would survive ("returns 0 instead of the
  discount and the test still passes").
- **Test code is code under review.** Apply the correctness and error-handling refs to it only
  where they change what the test proves. Debug leftovers in tests are nits (D3).
- **Severity.** "New logic without tests" is C2 (`refs/severity-and-output-format.md` §1), so major on
  an open path, but scale by the logic: branching on money, auth, persistence or parsing is major;
  thin glue is minor; exempt code is silence (see TEST-01).
- **Report test findings against the test line**, or against the first line of the untested logic
  for TEST-01.

## 2. Rule map

| ID | Defect | Languages | Default severity |
|---|---|---|---|
| TEST-01 | New or changed logic with no test | PY, NODE, TS | major (money/auth/data), else minor |
| TEST-02 | Vacuous test: asserts nothing real | PY, NODE, TS | major if it is the only test of the logic |
| TEST-03 | Self-confirming expected value | PY, NODE, TS | minor; major if the only test |
| TEST-04 | Over-mocking | PY, NODE, TS | minor; major if the mock hides the risk |
| TEST-05 | Flaky pattern: sleeps, clock, network, order | PY, NODE, TS | minor; major in required CI |
| TEST-06 | Disabled, focused or weakened test | PY, NODE, TS | major for `.only` and removed assertions |
| TEST-07 | Missing edge, negative or regression case | PY, NODE, TS | minor; major for untested denial |
| TEST-08 | Shared state and leaked side effects | PY, NODE, TS | minor |
| TEST-09 | Implementation-coupled UI tests | TS | minor |

## 3. Coverage of the change

### PY-TEST-01 · NODE-TEST-01 · TS-TEST-01 — New or changed logic with no test
- **Detect:** the diff adds or changes a function, branch, route, handler, reducer or hook in
  non-test code and no added or changed test references it; a fix (commit message, branch name or
  code shape) with no test that reproduces the bug. Anchor on the signature or the new branch and
  quote it.
  **Exempt (silence):** configuration, types and interfaces only, docs, generated code,
  re-exports, constants, migrations, logging-only changes, and thin pass-through wrappers.
  If the repository has no test setup at all, report that once as a minor, not per file.
- **Default severity:** major when the logic branches on money, auth, persistence, parsing or
  external input (C2/R1); minor for glue and presentation. Medium confidence unless you searched
  the test directories; low confidence becomes a question.
- **Why:** untested logic is verified only by whoever runs it first, in production.
- WRONG:
  ```python
  def apply_discount(total: Decimal, code: str | None, tier: str) -> Decimal:   # new in the diff
      if code == "WELCOME10" and tier != "enterprise":
          return total * Decimal("0.90")
      return total                                                              # no test in the diff
  ```
- CORRECT:
  ```python
  @pytest.mark.parametrize(
      ("code", "tier", "expected"),
      [("WELCOME10", "free", "90.00"), ("WELCOME10", "enterprise", "100.00"), (None, "free", "100.00")],
  )
  def test_apply_discount(code: str | None, tier: str, expected: str) -> None:
      assert apply_discount(Decimal("100.00"), code, tier) == Decimal(expected)
  ```
- **Fix:** name the cases the test must cover (each branch, one boundary, one failure); suggest
  the test, do not write the whole suite.
- **Cite:** Google Engineering Practices, "Code Review Developer Guide" ("Tests": tests should be
  included in the same change); pytest docs, "How to parametrize fixtures and test functions".
- **Tool code:** none (coverage tools report lines, not meaning).

### PY-TEST-07 · NODE-TEST-07 · TS-TEST-07 — Missing edge, negative or regression case
- **Detect:** validation, parsing, pagination, permission or money logic tested only with a valid,
  typical input; comparisons (`<`, `>=`, `len(x) == n`) with no test at, below and above the
  boundary; `raise` / `return 4xx` branches never exercised; an access-control test for the
  allowed role only, with no denied case; a bug fix whose test uses the already-working input.
  **Also look at the mock setup, not only at the test bodies:** a module-level `vi.mock` /
  `jest.mock` / `patch` factory whose auth, session, membership or permission lookup returns one
  fixed grant (`async () => ({ role: 'member' })`, `return_value=True`) and that no test overrides
  to deny. Every test then passes with the check deleted. Anchor on the factory line, not on a
  test.
- **Default severity:** minor (C3). Major when new authorization or validation logic has no test
  that proves a rejection (the behavior that matters is untested), including the always-granting
  mock above.
- **Why:** bugs sit at boundaries and in error branches; the happy path passes by design.
- WRONG:
  ```js
  test('admin can delete a project', async () => {
    const res = await request(app).delete('/projects/1').set(authAs('admin'));
    expect(res.status).toBe(204);                    // no test that a member gets 403
  });
  ```
  ```ts
  vi.mock('@/lib/db', () => ({
    db: { membership: { findUnique: vi.fn(async () => ({ role: 'member' })) } },  // always a member
  }));                                                 // no test makes it return null and expects a 403
  ```
- CORRECT:
  ```js
  test.each([['admin', 204], ['member', 403], [null, 401]])('DELETE /projects/1 as %s → %i', async (role, status) => {
    const res = await request(app).delete('/projects/1').set(authAs(role));
    expect(res.status).toBe(status);
  });
  ```
- **Fix:** add the boundary values (0, 1, max, empty, duplicate), the denied role and the failing
  input as table rows; for a bug fix, a test that fails on the old code; for a fixed-grant mock,
  `vi.mocked(db.membership.findUnique).mockResolvedValueOnce(null)` in a test that expects the
  rejection.
- **Cite:** ISTQB Foundation syllabus, boundary value analysis; Jest docs, `test.each`; pytest
  docs, "How to parametrize"; OWASP ASVS 4.0.3 V4.1 (access control at a trusted enforcement
  point; verify it denies).
- **Tool code:** none.

## 4. Assertion quality

### PY-TEST-02 · NODE-TEST-02 · TS-TEST-02 — Vacuous test: asserts nothing real
- **Detect:** a test body with no `assert` / `expect`; `assert True`; `assert response.status_code`
  (any non-zero status is truthy); `assert result` or `expect(result).toBeDefined()` /
  `.toBeTruthy()` on an object that is always defined; a bare comparison without `assert`
  (`result == 5`); a matcher not called (`expect(x).toBeTruthy`); `expect(fn).not.toThrow()` as the
  only check; `pytest.raises(Exception)`; `.resolves` / `.rejects` assertions that are not awaited
  or returned; an assertion inside an `if`, a loop or a callback that may not run;
  `try: … except: pass` in a test; an `async def` test without the plugin that runs it
  (pytest-asyncio or anyio), so the body never executes; a test function that is not collected
  (name not starting with `test`).
- **Default severity:** major when it is the only test of money, auth or persistence logic
  (C2/R1: false confidence); minor otherwise.
- **Why:** it passes whatever the code does.
- WRONG:
  ```python
  def test_create_order(client):
      response = client.post("/orders", json=PAYLOAD)
      assert response.status_code                  # 500 passes
      response.json()["total"] == 120              # no assert: the comparison is discarded
  ```
  ```js
  test('rejects a bad token', () => {
    expect(verify('bad')).rejects.toThrow();         // not awaited: the test ends first
  });
  ```
- CORRECT:
  ```python
  def test_create_order(client):
      response = client.post("/orders", json=PAYLOAD)
      assert response.status_code == 201
      assert response.json()["total"] == 120
  ```
  ```js
  test('rejects a bad token', async () => {
    await expect(verify('bad')).rejects.toThrow('invalid token');
  });
  ```
- **Fix:** assert the specific value, status or message; await promise matchers; assert on the
  outcome the user cares about.
- **Cite:** pytest docs, "Asserting with the `assert` statement" and "Assertions about expected
  exceptions"; Jest docs, `.resolves` / `.rejects` (return or await the assertion).
- **Tool code:** `[ruff: B015, B017, PT011, PT012, PT015]`,
  `[eslint: jest/expect-expect, jest/valid-expect, jest/no-conditional-expect, jest/no-standalone-expect]`.

### PY-TEST-03 · NODE-TEST-03 · TS-TEST-03 — Self-confirming expected value
- **Detect:** the expected value computed by the code under test or by a copy of its logic
  (`assert total(items) == sum(i.price * i.qty for i in items)` when `total` is that sum); the
  expectation taken from the same constant the code uses; a mock configured to return `X` and an
  assertion that the code returned `X` through the mock only; a snapshot or golden file written
  by the test run and committed without a human reading it.
- **Default severity:** minor; major when this is the only test of the logic.
- **Why:** the test restates the implementation, so a wrong implementation gives a matching wrong
  expectation.
- WRONG:
  ```python
  def test_tax():
      assert tax(Decimal("19.99")) == round(Decimal("19.99") * TAX_RATE, 2)   # same formula, same bug
  ```
- CORRECT:
  ```python
  def test_tax():
      assert tax(Decimal("19.99")) == Decimal("1.65")                # computed by hand, written as data
  ```
- **Fix:** hard-code expected values taken from the spec or a worked example; review snapshots
  line by line.
- **Cite:** Google Testing Blog, "Testing on the Toilet: Test Behavior, Not Implementation";
  Jest docs, "Snapshot Testing" (snapshots are reviewed as code).
- **Tool code:** none.

### PY-TEST-04 · NODE-TEST-04 · TS-TEST-04 — Over-mocking
- **Detect:** a test for module `M` that patches `M`'s own functions (`@patch("app.billing.calculate_tax")`
  in the billing tests; `jest.mock('./billing')` in `billing.test.js`); the database driver or ORM
  mocked in a test whose purpose is the query or the transaction; `patch("requests.get")` where the
  code imports `from requests import get` (the patch is in the wrong namespace, so the real call
  runs); `MagicMock()` / `jest.fn()` without a spec, so a misspelled method still passes; the only
  assertion is `assert_called_with` / `toHaveBeenCalledWith` and the behaviour (the return value or
  the stored row) is never checked.
- **Default severity:** minor; major when the mock replaces the thing at risk (the SQL, the
  serializer, the auth middleware) in the only test of that path (C2).
- **Why:** the test verifies the mock, not the code.
- WRONG:
  ```python
  @patch("app.billing.calculate_tax", return_value=Decimal("8.25"))
  def test_invoice_total(mock_tax):
      assert build_invoice(order).total == Decimal("108.25")        # tests arithmetic on a stub
  ```
- CORRECT:
  ```python
  def test_invoice_total(db_session):                                # real tax function, real session
      order = make_order(db_session, subtotal=Decimal("100.00"), region="TX")
      assert build_invoice(order).total == Decimal("108.25")
  ```
  ```python
  client = create_autospec(PaymentsClient, instance=True)           # a typo now raises AttributeError
  ```
- **Fix:** mock at the system boundary (network, clock, third-party SDK), use fakes or an
  in-memory database for your own layers, add `autospec` / typed mocks, and patch where the name is
  looked up.
- **Cite:** Google Testing Blog, "Testing on the Toilet: Don't Overuse Mocks"; Martin Fowler,
  "Mocks Aren't Stubs"; Python docs, `unittest.mock` ("Where to patch", `create_autospec`).
- **Tool code:** none.

## 5. Reliability

### PY-TEST-05 · NODE-TEST-05 · TS-TEST-05 — Flaky patterns
- **Detect:** `time.sleep(…)` / `await new Promise((r) => setTimeout(r, 500))` to wait for work;
  assertions on the real clock (`datetime.now()`, `Date.now()`) near a boundary; an unseeded
  `random` / `uuid4` in an expected value; real network calls or third-party sandboxes in unit
  tests; a fixed port; elapsed-time thresholds (`< 100 ms`); an assertion on iteration order of a
  `set` of strings or on an unsorted query (Python randomizes string hashing per process);
  `waitFor` with a side effect or several assertions inside; tests that pass only in UTC.
- **Default severity:** minor (C3). Major when the test needs the real network or clock in a
  required CI check (it fails whenever the dependency does).
- **Why:** a test that sometimes fails is ignored, and a real failure is then ignored too.
- WRONG:
  ```js
  fireEvent.click(getByText('Save'));
  await new Promise((r) => setTimeout(r, 1000));          // hope the request is done
  expect(getByText('Saved')).toBeInTheDocument();
  ```
  ```python
  def test_token_expiry():
      token = issue_token(ttl=1)
      time.sleep(1.1)
      assert is_expired(token)
  ```
- CORRECT:
  ```js
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Saved')).toBeInTheDocument();      // waits for the condition
  ```
  ```python
  def test_token_expiry(freezer):                                     # pytest-freezegun / time-machine
      token = issue_token(ttl=60)
      freezer.move_to(datetime.now(timezone.utc) + timedelta(seconds=61))
      assert is_expired(token)
  ```
- **Fix:** wait on a condition (`findBy*`, events), inject or freeze the clock, seed randomness,
  sort before comparing, fake the network.
- **Cite:** Martin Fowler, "Eradicating Non-Determinism in Tests"; Google Testing Blog, "Flaky
  Tests at Google and How We Mitigate Them"; Python docs, `PYTHONHASHSEED` / hash randomization;
  Jest docs, "Timer Mocks"; Testing Library docs, `waitFor` and `findBy`.
- **Tool code:** `[eslint: testing-library/no-wait-for-side-effects, testing-library/no-wait-for-multiple-assertions, testing-library/prefer-find-by]`.

### PY-TEST-06 · NODE-TEST-06 · TS-TEST-06 — Disabled, focused or weakened test
- **Detect:** `it.only` / `test.only` / `describe.only` / `fit` / `fdescribe` in the diff (CI then
  runs that one test and reports green); `.skip` / `xit` / `@pytest.mark.skip` / `@unittest.skip` /
  `xfail` with no reason or ticket; a deleted test or assertion that has no replacement in the
  same diff; an assertion loosened (`toEqual(obj)` → `toBeTruthy()`, `== 5` → `> 0`, a wider
  `pytest.approx` tolerance); snapshots regenerated wholesale; a coverage threshold lowered;
  `|| true` or `continue-on-error` added to the test step.
- **Default severity:** major for `.only` (the suite is silently narrowed) and for a removed or
  weakened assertion on logic that the diff still changes; minor for a skip that has a reason and a
  ticket; major for a skip with no reason on a test of the changed code. Minor for `.only` when
  the runner rejects it in CI (Vitest fails the run when `CI` is set, because `allowOnly`
  defaults to `!process.env.CI`): it still blocks local runs, but CI is not narrowed. Jest and
  pytest-style runners skip the rest silently.
- **Why:** the suite stays green while it checks less.
- WRONG:
  ```js
  describe.only('refunds', () => { … });          // every other file's tests are skipped
  it.skip('rounds half up', () => { … });          // no reason, no ticket
  ```
  ```python
  @pytest.mark.skip                                 # no reason
  def test_refund_over_limit(): ...
  ```
- CORRECT:
  ```js
  describe('refunds', () => { … });
  it.skip('rounds half up (TICKET-482: waiting on rounding spec)', () => { … });
  ```
  ```python
  @pytest.mark.xfail(reason="TICKET-482: rounding spec pending", strict=True)
  ```
- **Fix:** remove `.only`; give each skip a reason and an owner; restore or replace deleted
  assertions.
- **Cite:** Jest docs, `test.only` and `test.skip`; Vitest docs, `allowOnly`; pytest docs, "Skip
  and xfail" (reason, `strict`).
- **Tool code:** `[eslint: jest/no-focused-tests, jest/no-disabled-tests, jest/no-commented-out-tests]`;
  none for Python.

### PY-TEST-08 · NODE-TEST-08 · TS-TEST-08 — Shared state and leaked side effects
- **Detect:** a test that writes to the real database, a fixed file path or the home directory
  with no cleanup (`tmp_path` / `mkdtemp` not used); `os.environ[...] = …` or `process.env.X = …`
  without restoring (`monkeypatch.setenv` restores itself); module-level state that tests mutate
  (counters, caches, singletons); `test_b` that needs the data `test_a` created; `jest.spyOn`
  with no `restoreAllMocks` / `restoreMocks`; fakes for `Date`, `fetch` or timers left installed;
  a `scope="session"` fixture that tests modify.
- **Default severity:** minor (C3). It becomes visible when tests run in random order or in
  parallel.
- **Why:** tests that pass alone and fail together are expensive to debug.
- WRONG:
  ```python
  def test_feature_flag():
      os.environ["FEATURE_X"] = "1"            # stays set for every later test
      assert feature_enabled("x")
  ```
- CORRECT:
  ```python
  def test_feature_flag(monkeypatch):
      monkeypatch.setenv("FEATURE_X", "1")
      assert feature_enabled("x")
  ```
- **Fix:** fixtures with teardown, `tmp_path`, `monkeypatch`, per-test transactions rolled back,
  `afterEach(() => jest.restoreAllMocks())`.
- **Cite:** pytest docs, "How to monkeypatch/mock modules and environments" and `tmp_path`; Jest
  docs, `restoreMocks` and `jest.restoreAllMocks`.
- **Tool code:** none.

## 6. Frontend tests

### TS-TEST-09 — Implementation-coupled UI tests
- **Detect:** `container.querySelector('.btn-primary')`; `getByTestId` where a role, label or
  text query would work; reading component state, props or hook return values; `.find(Component)`
  or `instance()` from Enzyme-style APIs; `fireEvent.click` for a user interaction (`userEvent`
  models focus, keyboard and pointer events); `userEvent` or `findBy*` without `await`; a snapshot of
  a whole DOM subtree; `waitFor(() => expect(getBy…))` where `findBy…` does the same.
- **Default severity:** minor (C3).
- **Why:** such tests break on refactors that change nothing for users, and they pass on markup a
  keyboard or screen-reader user cannot operate; a role query fails when the control is not
  accessible.
- WRONG:
  ```tsx
  const { container } = render(<Cart items={items} />);
  fireEvent.click(container.querySelector('.cart__checkout')!);
  expect(container.querySelector('.cart__total')!.textContent).toBe('$120.00');
  ```
- CORRECT:
  ```tsx
  const user = userEvent.setup();
  render(<Cart items={items} />);
  await user.click(screen.getByRole('button', { name: /checkout/i }));
  expect(screen.getByText('$120.00')).toBeInTheDocument();
  ```
- **Fix:** query by role, label or text in that order of preference; `await user.*`; assert what
  the user sees.
- **Cite:** Testing Library docs, "Guiding Principles" and "About Queries" (priority: `getByRole`
  first); user-event docs, "Introduction" (`setup()` and awaited calls).
- **Tool code:** `[eslint: testing-library/no-container, testing-library/no-node-access, testing-library/prefer-screen-queries, testing-library/await-async-queries, testing-library/prefer-find-by]`.

## 7. Do not flag

| Pattern | Why it is not a finding |
|---|---|
| No test for a config, type-only, docs, generated or migration change | exempt (TEST-01) |
| The test lives in a file the diff does not touch and you found it by search | covered; at most a question about whether it covers the new branch |
| A mocked network, clock, payment SDK or email gateway | that is the system boundary; mock it |
| `getByTestId` for an element with no role, label or text | the documented last resort |
| `time.sleep` / `setTimeout` inside a fake or a retry helper under test | part of the behavior being tested |
| `assert` with no message | style; pytest introspects it |
| Low line coverage with no new logic in the diff | not caused by this change |
| Debug `print` or `console.log` in a test | nit, see `refs/diff-hygiene.md` |
