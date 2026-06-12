# Testing — Python Reference

Grounded in the **pytest** docs and the `unittest.mock` docs. Tests are specifications of
behavior; they should read clearly and fail informatively.

## Arrange-Act-Assert

Structure each test in three visible phases: set up inputs, perform the one action under test, then
assert on the outcome. One behavior per test — a test name should describe the behavior it pins.

```python
# WRONG — no structure, vague name, several behaviors tangled together
def test_user():
    u = User("a@b.com")
    assert u.email == "a@b.com"
    u.deactivate()
    assert not u.is_active
    assert u.audit_log[-1] == "deactivated"
```

```python
# CORRECT — one behavior, AAA shape, descriptive name
def test_deactivate_marks_user_inactive() -> None:
    user = User("a@b.com")          # Arrange
    user.deactivate()               # Act
    assert user.is_active is False  # Assert
```

Use plain `assert` (pytest rewrites it for rich failure output) — not `self.assertEqual`. Assert on
specific values, not just truthiness.

## Fixtures for setup, not module-level globals

`@pytest.fixture` provides reusable, isolated setup with teardown via `yield`. Prefer fixtures over
shared module state, which leaks between tests.

```python
import pytest

@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url="http://test") as c:
        yield c                      # teardown (close) runs after the test

def test_health(client: httpx.Client) -> None:
    assert client.get("/health").status_code == 200
```

Use `tmp_path` for filesystem tests and `monkeypatch` for env vars / attributes — both are
built-in fixtures that auto-clean.

```python
def test_reads_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "test-key")
    assert load_config().api_key == "test-key"
```

## Parametrize input matrices instead of copy-pasting

`@pytest.mark.parametrize` turns N near-identical tests into one, with each case reported
separately.

```python
# WRONG — three tests that differ only in data
def test_even_2(): assert is_even(2)
def test_even_0(): assert is_even(0)
def test_even_3(): assert not is_even(3)
```

```python
# CORRECT
@pytest.mark.parametrize(
    ("n", "expected"),
    [(2, True), (0, True), (3, False), (-4, True)],
)
def test_is_even(n: int, expected: bool) -> None:
    assert is_even(n) is expected
```

## Mock at boundaries, not internals

Mock the *edges* of your system — network, clock, filesystem, third-party SDKs — so tests are fast
and deterministic. Do **not** mock the very logic you are testing; that asserts on your mocks, not
your code. Patch where the name is *used*, not where it is defined.

```python
# WRONG — over-mocking: the test now verifies the mock, not real behavior
def test_total(mocker):
    cart = mocker.Mock()
    cart.total.return_value = 30
    assert cart.total() == 30        # tests nothing real
```

```python
# CORRECT — mock the external boundary; test your real logic against it
def test_checkout_charges_gateway(mocker) -> None:
    charge = mocker.patch("myapp.checkout.gateway.charge", return_value="ch_123")
    receipt = checkout(cart=Cart(items=[Item("sku", 1000)]))   # real logic runs
    charge.assert_called_once_with(amount=1000, currency="usd")
    assert receipt.charge_id == "ch_123"
```

Prefer a real lightweight fake (in-memory repo, `tmp_path`) over a mock when feasible — it exercises
more real behavior.

## Test behavior and edges, not coverage for its own right

Aim coverage at meaningful paths: the happy path, boundary values, and the error/exception
branches. A test that asserts an exception is raised is as important as the success case.

```python
def test_withdraw_over_balance_raises() -> None:
    account = Account(balance=50)
    with pytest.raises(InsufficientFunds):
        account.withdraw(100)
```

Layout: keep tests in a top-level `tests/` mirroring the package, files named `test_*.py`,
functions `test_*`. Run a single test with
`pytest tests/test_account.py::test_withdraw_over_balance_raises -v`.
