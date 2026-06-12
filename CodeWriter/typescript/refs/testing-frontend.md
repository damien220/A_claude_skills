# Frontend Testing — TypeScript Frontend Reference

Grounded in the **React Testing Library docs** ("Guiding Principles"), the **Vitest docs**, the
**MSW docs**, and **Kent C. Dodds — Testing Trophy / "Common mistakes with RTL"**. Stack:
**Vitest + React Testing Library + userEvent + MSW**, `jsdom` environment.

---

## The guiding principle

> "The more your tests resemble the way your software is used, the more confidence they can
> give you." — RTL docs

Test what the user sees and does; never component internals (state, instance methods, child
props). Internals-coupled tests break on refactors that change nothing observable — the
definition of a bad test.

```ts
// vitest.config.ts
export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
});
```

---

## Query priority: role > label > text > testid

(Source: RTL docs — "About Queries / Priority".) Role queries double as a passive accessibility
check — if `getByRole('button', { name: 'Save' })` can't find it, neither can a screen reader.

```tsx
// WRONG — implementation-coupled selectors
const { container } = render(<LoginForm />);
container.querySelector('.submit-btn');
screen.getByTestId('email-input');          // testid when a label exists

// CORRECT — accessible queries
render(<LoginForm />);
screen.getByRole('textbox', { name: /email/i });
screen.getByLabelText(/password/i);
screen.getByRole('button', { name: /sign in/i });
```

`getByTestId` is the last resort for elements with no accessible role (e.g. a decorative
wrapper you must assert on).

---

## `userEvent` over `fireEvent`

`userEvent` dispatches the full real-browser event sequence (pointerdown → focus → keydown →
input…), catching bugs `fireEvent`'s single synthetic event misses. Always `setup()` first;
all calls are async. (Source: RTL user-event docs.)

```tsx
// WRONG
fireEvent.change(input, { target: { value: 'ada@example.com' } });
fireEvent.click(button);

// CORRECT
const user = userEvent.setup();
await user.type(screen.getByLabelText(/email/i), 'ada@example.com');
await user.click(screen.getByRole('button', { name: /sign in/i }));
```

---

## MSW — mock the network, not the fetch

Mocking `fetch`/axios couples tests to the HTTP client. MSW intercepts at the network level —
components run their real data path (real `apiFetch`, real Zod parsing). (Source: MSW docs.)

```ts
// src/test/handlers.ts
import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('/api/users', () =>
    HttpResponse.json([{ id: '1', name: 'Ada', email: 'ada@example.com', role: 'member' }])
  ),
];

// src/test/setup.ts
import { setupServer } from 'msw/node';
export const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());     // per-test overrides don't leak
afterAll(() => server.close());
```

```tsx
// Per-test error case — override just this handler
server.use(http.get('/api/users', () => HttpResponse.json(problem500, { status: 500 })));
```

---

## Async assertions — `findBy*`, never timeouts

```tsx
// WRONG — flaky sleep; arbitrary number
await new Promise((r) => setTimeout(r, 500));
expect(screen.getByText('Ada')).toBeInTheDocument();

// CORRECT — findBy* polls until it appears (or times out with a useful error)
expect(await screen.findByText('Ada')).toBeInTheDocument();

// CORRECT — asserting disappearance
await waitForElementToBeRemoved(() => screen.queryByRole('progressbar'));
```

One assertion style trap: `waitFor` with multiple assertions retries them as a block — keep one
assertion per `waitFor` (`testing-library/no-wait-for-multiple-assertions`).

---

## AAA structure, one behavior per test

```tsx
// CORRECT — renderWithProviders wraps QueryClientProvider etc. once, in test/utils.tsx
describe('UserList', () => {
  it('shows users returned by the API', async () => {
    // Arrange
    renderWithProviders(<UserList />);
    // Act — (initial fetch is the act)
    // Assert
    expect(await screen.findByText('Ada')).toBeInTheDocument();
  });

  it('shows a retryable error when the API fails', async () => {
    server.use(http.get('/api/users', () => HttpResponse.error()));
    renderWithProviders(<UserList />);

    expect(await screen.findByRole('alert')).toHaveTextContent(/went wrong/i);
    expect(screen.getByRole('button', { name: /retry/i })).toBeEnabled();
  });
});
```

```tsx
// test/utils.tsx — fresh QueryClient per test; retries off so error tests don't hang
export function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}
```

Reset between tests: `vi.clearAllMocks()` in `beforeEach`; MSW `server.resetHandlers()` in
`afterEach`.

---

## Testing custom hooks

Render the hook through a component when possible (test behavior); `renderHook` for pure-logic
hooks with no UI.

```tsx
// CORRECT
const { result } = renderHook(() => useDebounce('a', 200));
expect(result.current).toBe('a');
```

---

## Accessibility assertions

Run axe on every component that renders interactive UI. (Source: vitest-axe / jest-axe docs.)

```tsx
import { axe } from 'vitest-axe';

it('has no accessibility violations', async () => {
  const { container } = renderWithProviders(<SignUpForm onSignUp={vi.fn()} />);
  expect(await axe(container)).toHaveNoViolations();
});
```

---

## What to test, what not to

| Test | Skip |
|---|---|
| Render output per state (loading/error/data/empty) | Styling and layout pixel values |
| Interaction outcomes (click → mutation → UI change) | That React/TanStack/RHF themselves work |
| Form validation messages and submit blocking | Implementation details (state values, handler identity) |
| Accessibility (axe + role queries) | Snapshot tests of whole trees (brittle, review-blind) |
| Edge cases: empty lists, long text, 0/negative numbers | |

Coverage target: 80%+ on feature components and hooks; don't chase coverage on presentational
wrappers.
