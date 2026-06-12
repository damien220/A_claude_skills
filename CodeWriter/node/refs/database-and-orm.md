# Database & ORM — Node.js Reference

Grounded in **Prisma docs**, **Drizzle ORM docs**, the **Encore 2025 ORM comparison**, and
**LogRocket Drizzle vs Prisma 2025**. The data layer is where the most irreversible bugs live —
wrong transaction boundaries, N+1 queries, and missing migrations corrupt data silently.

---

## ORM selection — Prisma vs Drizzle

Neither is universally better. Choose based on project characteristics:

| Criterion | **Prisma** | **Drizzle** |
|---|---|---|
| **Developer experience** | Schema-first (`prisma.schema`); auto-generated migrations; Prisma Studio | SQL-native; you write SQL-adjacent TypeScript; manual migrations with `drizzle-kit` |
| **Type safety** | Auto-generated client from schema; fully typed queries | TypeScript-first; types derived from schema definitions in code |
| **Performance** | Slightly slower on complex queries; connection pool via Prisma Accelerate | ~3–5× faster on equivalent queries; minimal overhead; ~5 KB bundle |
| **Serverless / edge** | Cold start cost; Prisma Accelerate needed for edge | Excellent — lightweight, runs in Workers/Lambda without cold start penalty |
| **Migrations** | First-class migration workflow (`prisma migrate dev / deploy`) | `drizzle-kit generate + push`; migrations as SQL files |
| **Transactions** | `$transaction([...])` or interactive transactions | `db.transaction(async (tx) => {...})` |
| **Raw SQL escape** | `prisma.$queryRaw` with `Prisma.sql` template tag | First-class: mix SQL and ORM freely |

**Decision rule:**
- New product backend, team prioritizes DX → **Prisma**
- Serverless / edge / performance-critical / you want full SQL control → **Drizzle**
- Avoid **TypeORM** for new projects (decorator-based, more runtime surprises, slower maintenance)

```ts
// Prisma setup
// prisma/schema.prisma
model User {
  id        String   @id @default(cuid())
  email     String   @unique
  name      String
  createdAt DateTime @default(now())
  orders    Order[]
}

// In code — fully typed
import { PrismaClient } from '@prisma/client';
const prisma = new PrismaClient();

const user = await prisma.user.findUnique({
  where: { id },
  select: { id: true, email: true, name: true },  // always select: never fetch entire row
});
```

```ts
// Drizzle setup
// db/schema.ts
import { pgTable, text, timestamp } from 'drizzle-orm/pg-core';

export const users = pgTable('users', {
  id:        text('id').primaryKey(),
  email:     text('email').notNull().unique(),
  name:      text('name').notNull(),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

// In code
import { db } from './db.js';
import { eq } from 'drizzle-orm';
import { users } from './schema.js';

const user = await db.select({ id: users.id, email: users.email })
  .from(users)
  .where(eq(users.id, id))
  .limit(1);
```

---

## Transactions — always wrap multi-step mutations

Any operation that modifies more than one row or table must be wrapped in a transaction.
Without a transaction, a failure halfway through leaves the database in a partially-mutated state.

```ts
// WRONG — two operations with no transaction; if the second fails, payment exists without order
const payment = await prisma.payment.create({ data: { amount, userId } });
const order   = await prisma.order.create({ data: { paymentId: payment.id, userId } });
```

```ts
// CORRECT — Prisma sequential transaction
const [payment, order] = await prisma.$transaction([
  prisma.payment.create({ data: { amount, userId } }),
  prisma.order.create({ data: { userId } }),           // paymentId added in second step
]);

// CORRECT — Prisma interactive transaction (needed when result of step 1 feeds step 2)
const order = await prisma.$transaction(async (tx) => {
  const payment = await tx.payment.create({ data: { amount, userId } });
  return tx.order.create({ data: { paymentId: payment.id, userId } });
});
// Either both succeed or both roll back; no partial state ever reaches the DB
```

```ts
// CORRECT — Drizzle transaction
const order = await db.transaction(async (tx) => {
  const [payment] = await tx.insert(payments).values({ amount, userId }).returning();
  const [order]   = await tx.insert(orders).values({ paymentId: payment.id, userId }).returning();
  return order;
});
```

**Isolation level:** Use the database default (`READ COMMITTED`) unless you have a specific
concurrency reason to use `SERIALIZABLE`. Elevating isolation increases lock contention.

---

## N+1 queries — the silent performance killer

An N+1 query is when fetching a list of N records triggers N additional queries — one per record.
It is the most common ORM antipattern and scales linearly with data size.

```ts
// WRONG — N+1: one query to get 100 users, then 100 queries to get each user's orders
const users = await prisma.user.findMany();       // 1 query → 100 users
for (const user of users) {
  const orders = await prisma.order.findMany({    // 100 queries
    where: { userId: user.id },
  });
  user.orders = orders;
}
```

```ts
// CORRECT — eager load in one query with include/select
const users = await prisma.user.findMany({
  include: {
    orders: {
      select: { id: true, total: true, createdAt: true },  // select only needed fields
      where: { status: 'completed' },
      orderBy: { createdAt: 'desc' },
      take: 10,          // limit related records to prevent mega-payloads
    },
  },
});
// 1 query total; Prisma generates a JOIN
```

```ts
// CORRECT — Drizzle: explicit join
const result = await db
  .select({
    userId:     users.id,
    email:      users.email,
    orderId:    orders.id,
    orderTotal: orders.total,
  })
  .from(users)
  .leftJoin(orders, eq(orders.userId, users.id))
  .where(eq(orders.status, 'completed'));
```

**Rule:** Every `findMany()` call that renders a list must have an explicit `select` or `include`.
No bare `prisma.user.findMany()` in route handlers — the implicit "select *" fetches columns you
don't need and hides potential N+1s.

---

## Migrations — never modify the schema directly

Schema changes in production must go through a migration file. Direct DDL (e.g.
`ALTER TABLE users ADD COLUMN ...` run manually) bypasses Prisma's migration history and
breaks `prisma migrate deploy` in CI/CD.

```bash
# Prisma workflow
# Development: generates migration file + applies it to dev DB
npx prisma migrate dev --name add_user_role

# CI / Production: applies pending migrations; fails if schema drift detected
npx prisma migrate deploy

# Inspect diff (never run directly in prod — generate a migration first)
npx prisma migrate diff --from-schema-datamodel prisma/schema.prisma \
                        --to-schema-datasource prisma/schema.prisma
```

```bash
# Drizzle workflow
npx drizzle-kit generate   # generates SQL migration file in drizzle/ directory
npx drizzle-kit migrate    # applies pending migrations
npx drizzle-kit studio     # visual schema browser (dev only)
```

**Rules:**
- Migration files are committed to git — they are source of truth for schema history
- Never edit an applied migration file — create a new one with the correction
- `migrate deploy` runs as the first step of every production deployment (before the server starts)
- Test migrations on a staging database with production-sized data before deploying to prod

---

## Connection pool configuration

Too few connections starve the application under load. Too many exhaust the database server
(PostgreSQL default max connections: 100). Size deliberately.

```ts
// CORRECT — Prisma connection pool
// In DATABASE_URL: ?connection_limit=10&pool_timeout=10
// Or via PrismaClient datasource:
const prisma = new PrismaClient({
  datasources: {
    db: {
      url: `${env.DATABASE_URL}?connection_limit=${poolSize}&pool_timeout=10`,
    },
  },
  log: process.env.NODE_ENV === 'development' ? ['query', 'warn', 'error'] : ['warn', 'error'],
});

// Recommended pool size formula:
// poolSize = (number_of_app_instances) × (CPU_cores × 2) but ≤ DB max_connections / app_instances
```

```ts
// CORRECT — pg Pool configuration
import { Pool } from 'pg';
import os from 'node:os';

export const pool = new Pool({
  connectionString: env.DATABASE_URL,
  max:                   Math.max(4, os.cpus().length * 2),  // 2× CPU, min 4
  idleTimeoutMillis:     30_000,   // return idle connection to pool after 30s
  connectionTimeoutMillis: 5_000,  // fail fast if pool is exhausted
  allowExitOnIdle:       true,     // allow process to exit if pool is idle (tests)
});

// Expose pool metrics for monitoring
pool.on('error', (err) => logger.error({ err }, 'Unexpected DB pool error'));
```

---

## Soft deletes — `deletedAt` column pattern

Hard deletes are irreversible and break foreign key constraints in audit tables. Soft deletes
mark rows as deleted without removing them, enabling data recovery and audit trails.

```ts
// Prisma — soft delete pattern
model User {
  id        String    @id @default(cuid())
  email     String    @unique
  deletedAt DateTime?          // null = active; non-null = deleted
}

// Query helper — always filter out deleted rows
const activeUsers = await prisma.user.findMany({
  where: { deletedAt: null },
});

// Soft delete
await prisma.user.update({
  where: { id },
  data: { deletedAt: new Date() },
});
```

**Note:** With Prisma, use `prisma-soft-delete-middleware` or a custom Prisma extension to
apply `deletedAt: null` filter globally so you cannot accidentally expose deleted records.

---

## Query result types — always `select`, never `findFirst` without limits

```ts
// WRONG — fetches all columns including sensitive ones (passwordHash, internalNotes, etc.)
const user = await prisma.user.findFirst({ where: { email } });

// WRONG — no LIMIT on findMany; returns entire table
const allUsers = await prisma.user.findMany();
```

```ts
// CORRECT — explicit select; LIMIT on list queries
const user = await prisma.user.findUnique({
  where: { email },
  select: { id: true, name: true, email: true, role: true },
});

const users = await prisma.user.findMany({
  take: 50,       // always limit; pair with cursor pagination for paging
  orderBy: { createdAt: 'desc' },
  select: { id: true, name: true, email: true },
});
```
