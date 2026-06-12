# Testing — Node.js Web Reference

Grounded in **Vitest docs**, **Fastify testing docs**, **Supertest docs**, and the
**Vitest vs Jest 2025 benchmark**. The target stack: Vitest for unit and integration tests,
`fastify.inject()` or Supertest for HTTP-level integration tests.

---

## Test runner: Vitest for new projects

| Runner | Use when | Why |
|---|---|---|
| **Vitest** | New TypeScript projects | Native ESM, TS support without config, 10–20× faster in watch mode, Jest-compatible API |
| **Jest** | Existing Jest codebase | No need to migrate; Jest 30 improved performance significantly |
| **`node:test`** | Minimal deps / scripting | Built-in, zero install, sufficient for simple modules |

```ts
// Vitest test file — same API as Jest; just import from 'vitest'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
```

---

## HTTP integration tests — inject, not real ports

Starting a real HTTP server for tests is slow, allocates OS ports, and creates teardown
complexity. Fastify's `inject()` and Supertest both exercise the full request-response cycle
without binding a port.

```ts
// WRONG — real server; port allocation, race conditions in parallel test suites
const server = app.listen(3000);
const res = await fetch('http://localhost:3000/users');
server.close();
```

```ts
// CORRECT — Fastify inject: full request lifecycle, no port
// tests/users.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { buildApp } from '../src/app.js';
import type { FastifyInstance } from 'fastify';

describe('GET /users', () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    app = await buildApp({ env: 'test' });
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  it('returns 200 with an array of users', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/users',
      headers: { authorization: 'Bearer test-token' },
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject([
      expect.objectContaining({ id: expect.any(String), email: expect.any(String) }),
    ]);
  });

  it('returns 401 when authorization header is missing', async () => {
    const response = await app.inject({ method: 'GET', url: '/users' });
    expect(response.statusCode).toBe(401);
    expect(response.json()).toMatchObject({ status: 401, type: expect.any(String) });
  });
});
```

```ts
// CORRECT — Express + Supertest
import request from 'supertest';
import { buildApp } from '../src/app.js';

describe('POST /users', () => {
  const app = buildApp();

  it('creates a user and returns 201', async () => {
    const res = await request(app)
      .post('/users')
      .send({ email: 'alice@example.com', name: 'Alice', password: 'correcthorsebattery' })
      .expect(201);

    expect(res.body).toMatchObject({ id: expect.any(String), email: 'alice@example.com' });
  });
});
```

---

## Test structure — describe / it / AAA

```ts
// CORRECT — three-level nesting; Arrange-Act-Assert inside each it()
describe('UserService', () => {
  describe('createUser()', () => {
    it('returns the new user with an ID', async () => {
      // Arrange
      const input = { email: 'bob@example.com', name: 'Bob' };

      // Act
      const user = await userService.createUser(input);

      // Assert
      expect(user.id).toBeDefined();
      expect(user.email).toBe(input.email);
    });

    it('throws ValidationError when email is already taken', async () => {
      await userService.createUser({ email: 'dupe@example.com', name: 'First' });

      await expect(
        userService.createUser({ email: 'dupe@example.com', name: 'Second' })
      ).rejects.toThrow(ValidationError);
    });
  });
});
```

Each `it()` tests one observable behavior. An assertion failure should tell you exactly what
broke without reading the test body — write the description accordingly.

---

## Mock at system boundaries — never internal logic

Mock the DB client, HTTP client, and external service SDKs. Never mock a function inside the
same module you are testing — that tests the mock, not the code.

```ts
// WRONG — mocking internal function; test passes even if the logic is broken
vi.mock('./user-service.js', () => ({
  createUser: vi.fn().mockResolvedValue({ id: '1', email: 'a@b.com' }),
}));
// The route handler is untested; you're just testing that vi.fn() returns what you told it
```

```ts
// CORRECT — mock the DB layer (external boundary); test the service logic
// db.ts — the boundary
import { db } from './db.js';

vi.mock('./db.js', () => ({
  db: {
    user: {
      create: vi.fn(),
      findUnique: vi.fn(),
    },
  },
}));

import { createUser } from './user-service.js';

describe('createUser()', () => {
  beforeEach(() => {
    vi.mocked(db.user.create).mockResolvedValue({
      id: 'user-1',
      email: 'alice@example.com',
      name: 'Alice',
      createdAt: new Date(),
    });
  });

  afterEach(() => vi.clearAllMocks());

  it('returns the created user', async () => {
    const user = await createUser({ email: 'alice@example.com', name: 'Alice' });
    expect(user.id).toBe('user-1');
    expect(db.user.create).toHaveBeenCalledOnce();
  });
});
```

---

## Reset mocks between tests — prevent leakage

Mocks that carry state between tests create flaky, order-dependent test suites.

```ts
// WRONG — mock state from test 1 leaks into test 2
describe('payment tests', () => {
  it('test 1', async () => {
    vi.mocked(stripe.charges.create).mockResolvedValue({ id: 'ch_1' });
    // ... test passes
  });

  it('test 2', async () => {
    // stripe.charges.create is still mocked from test 1!
    // If test 1 failed before clearing the mock, this test may pass for the wrong reason
  });
});
```

```ts
// CORRECT — reset in beforeEach or use clearMocks: true in vitest.config.ts
// vitest.config.ts
import { defineConfig } from 'vitest/config';
export default defineConfig({
  test: {
    clearMocks: true,      // vi.clearAllMocks() before each test automatically
    globals: true,
  },
});
```

---

## Fixtures — reusable test data and server setup

```ts
// CORRECT — vitest fixtures for shared server lifecycle
// tests/fixtures.ts
import type { FastifyInstance } from 'fastify';
import { buildApp } from '../src/app.js';

export async function withApp(
  fn: (app: FastifyInstance) => Promise<void>
): Promise<void> {
  const app = await buildApp({ env: 'test' });
  await app.ready();
  try {
    await fn(app);
  } finally {
    await app.close();
  }
}

// Usage
it('creates a user', () =>
  withApp(async (app) => {
    const res = await app.inject({ method: 'POST', url: '/users', payload: testUser });
    expect(res.statusCode).toBe(201);
  }));
```

---

## Async tests — always async/await

```ts
// WRONG — done callback; easy to forget, leads to false positives if done() never called
it('loads user', (done) => {
  getUser('1').then((user) => {
    expect(user.id).toBe('1');
    done();
  });
});
```

```ts
// CORRECT — async/await; test fails cleanly if the assertion throws
it('loads user', async () => {
  const user = await getUser('1');
  expect(user.id).toBe('1');
});

// Testing that a rejection occurs
it('throws NotFoundError for unknown ID', async () => {
  await expect(getUser('unknown')).rejects.toThrow(NotFoundError);
});
```

---

## Coverage — target behavior, not lines

Coverage is a signal about untested behavior, not a quality score. 100% line coverage with
trivial tests is meaningless. Prioritize:

1. Business logic in service layers (high value — errors here have real consequences)
2. Route handlers (validate request → response contracts)
3. Error paths (not just happy paths)

```ts
// vitest.config.ts — coverage with meaningful thresholds
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      thresholds: {
        branches: 80,
        functions: 80,
        lines: 80,
      },
      exclude: ['src/config.ts', 'src/logger.ts', 'dist/**'],
    },
  },
});
```

---

## Snapshot tests — narrow scope

Snapshot tests are high-value for serialization output (error response shapes, email templates,
CLI output). They are low-value for business logic — they test that the code produces the same
output as it did when the snapshot was written, not that the output is correct.

```ts
// CORRECT — snapshot test for the RFC 9457 error serializer
it('serializes NotFoundError as RFC 9457', () => {
  const err = new NotFoundError('User', 'abc123');
  const response = serializeError(err, '/users/abc123');
  expect(response).toMatchSnapshot();
});

// snapshot file records the exact shape; changes force a deliberate review
```

Never snapshot large objects with timestamps or UUIDs — snapshots become flaky and obscure
real regressions in the fixed parts of the output.
