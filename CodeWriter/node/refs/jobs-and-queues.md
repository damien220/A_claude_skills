# Background Jobs & Queues — Node.js Reference

Grounded in **BullMQ docs**, the **JudoScale Node.js task queue comparison 2025**, and
**AppSignal Bull vs Agenda**. Background jobs are the escape valve for work that must not block
the HTTP request cycle — email delivery, image processing, report generation, webhooks.

---

## Job queue selection

| Library | Backend | Use when |
|---|---|---|
| **BullMQ** | Redis | Default recommendation for new projects. TypeScript-native, actively maintained, priority queues, rate limiting, cron jobs, built-in UI (`@bull-board`) |
| **Agenda** | MongoDB | Your infra already has MongoDB and you don't want Redis; human-readable cron-like scheduling; less active development than BullMQ |
| **node-cron** | In-memory | Single-process cron jobs only; no persistence, no retries, no concurrency control — dev tools or simple non-critical scheduled tasks |
| **`node:timers`** | In-memory | One-off deferred execution in a single process; never for production work queues |

**Rule:** If work must survive a process crash, use **BullMQ** (Redis). If work can be lost on
restart (cache warming, metrics flush), in-memory timers are acceptable.

---

## BullMQ basics — producer / worker pattern

Separate concerns: the API process adds jobs (producer); a dedicated worker process consumes
them. Never run heavy workers in the same process as the HTTP server.

```ts
// lib/queues.ts — shared queue definitions
import { Queue } from 'bullmq';
import { redis } from './redis.js';

export const emailQueue = new Queue('email', {
  connection: redis,
  defaultJobOptions: {
    attempts:    3,
    backoff:     { type: 'exponential', delay: 2_000 },   // 2s, 4s, 8s
    removeOnComplete: { age: 60 * 60 * 24 },               // keep for 24h for monitoring
    removeOnFail:     { age: 60 * 60 * 24 * 7 },           // keep failed for 7 days
  },
});

export const reportQueue = new Queue('report', { connection: redis });
```

```ts
// api/routes/users.ts — producer: add jobs from the HTTP layer
import { emailQueue } from '../lib/queues.js';

fastify.post('/users', async (request, reply) => {
  const user = await userService.create(request.body);

  // Add job — returns immediately; worker handles it asynchronously
  await emailQueue.add('welcome-email', { userId: user.id, email: user.email });

  return reply.status(201).send(user);
});
```

```ts
// workers/email-worker.ts — consumer: separate process
import { Worker } from 'bullmq';
import { redis } from '../lib/redis.js';
import { sendWelcomeEmail } from '../lib/mailer.js';

const worker = new Worker(
  'email',
  async (job) => {
    if (job.name === 'welcome-email') {
      await sendWelcomeEmail(job.data.userId, job.data.email);
    }
  },
  {
    connection: redis,
    concurrency: 5,       // process up to 5 jobs in parallel
  }
);

worker.on('failed', (job, err) => {
  logger.error({ jobId: job?.id, err }, 'Email job failed');
});

worker.on('completed', (job) => {
  logger.info({ jobId: job.id, name: job.name }, 'Email job completed');
});
```

---

## Retry & backoff — all jobs must declare these

A job without a retry policy is a silent failure. An uncontrolled retry without backoff
hammers the failing dependency.

```ts
// WRONG — no retry policy; if email delivery fails once, the email is never sent
await emailQueue.add('welcome-email', { userId }, {});
```

```ts
// CORRECT — exponential backoff; dead-letter queue (DLQ) on exhaustion
await emailQueue.add('send-invoice', { invoiceId }, {
  attempts: 5,
  backoff: {
    type:  'exponential',
    delay: 2_000,   // 2s, 4s, 8s, 16s, 32s — max total wait ~62s
  },
  // Job lands in the failed set (acts as DLQ) on final failure
  // Monitor with @bull-board or custom metrics endpoint
});
```

**Retry policy table:**

| Job type | `attempts` | Backoff delay | Rationale |
|---|---|---|---|
| Email / SMS delivery | 5 | exponential 2s | Transient SMTP failures; 62s max wait |
| Webhook outbound | 7 | exponential 1s | Third-party APIs often have brief outages |
| DB-only side effects | 3 | fixed 500ms | DB issues resolve quickly |
| S3 file processing | 3 | exponential 5s | Large uploads may briefly exceed rate limits |
| External payment API | 3 | exponential 10s | Payment APIs have strict rate limits |

---

## Dead-letter queue (DLQ) — handle permanent failures

Failed jobs (exhausted all retries) land in BullMQ's `failed` state. Treat it as a DLQ:
monitor its size, alert on growth, and have a process to requeue or manually resolve them.

```ts
// Monitor DLQ size and alert
async function checkDlqHealth(): Promise<void> {
  const counts = await emailQueue.getJobCounts('failed', 'delayed', 'active');
  metrics.gauge('queue.email.failed',  counts.failed);
  metrics.gauge('queue.email.delayed', counts.delayed);
  metrics.gauge('queue.email.active',  counts.active);

  if (counts.failed > 100) {
    logger.warn({ count: counts.failed }, 'Email DLQ backlog exceeding threshold');
  }
}

// Requeue failed jobs (manual intervention or automated recovery)
async function requeueFailed(queueName: string, limit = 50): Promise<number> {
  const queue = new Queue(queueName, { connection: redis });
  const failed = await queue.getFailed(0, limit - 1);
  await Promise.all(failed.map((job) => job.retry()));
  return failed.length;
}
```

---

## Idempotency — jobs must be safe to run twice

Networks fail between "job added" and "job acknowledged". BullMQ can run a job more than once
in edge cases. Every job must be **idempotent**: running it twice produces the same outcome as
running it once.

```ts
// WRONG — running twice charges the customer twice
async function processPaymentJob(job: Job): Promise<void> {
  await stripeClient.charge({ amount: job.data.amount, customerId: job.data.customerId });
}
```

```ts
// CORRECT — idempotency key prevents double-charge
async function processPaymentJob(job: Job): Promise<void> {
  const idempotencyKey = `payment-${job.id}`;  // stable per job; same key = same result

  const alreadyProcessed = await redis.get(`processed:${idempotencyKey}`);
  if (alreadyProcessed) {
    logger.info({ jobId: job.id }, 'Payment already processed — skipping');
    return;
  }

  await stripeClient.charge({
    amount:         job.data.amount,
    customerId:     job.data.customerId,
    idempotencyKey,                           // Stripe uses this to deduplicate server-side too
  });

  await redis.set(`processed:${idempotencyKey}`, '1', 'EX', 60 * 60 * 24);  // 24h TTL
}
```

**Idempotency patterns:**
- Use `job.id` as the idempotency key — stable across retries
- Check-and-set in Redis with a TTL longer than the max retry window
- For DB mutations, use `INSERT ... ON CONFLICT DO NOTHING` with a unique constraint

---

## Distributed locking — prevent concurrent execution of singleton jobs

Some jobs must run exactly once at a time (nightly report generation, cache warming, billing
cycle). Multiple workers without a lock will double-execute.

```ts
// CORRECT — Redis distributed lock for singleton jobs
import Redlock from 'redlock';
import { redis } from './redis.js';

const redlock = new Redlock([redis], {
  driftFactor: 0.01,    // 1% clock drift allowed
  retryCount:  0,        // fail immediately if lock not acquired (don't queue)
  retryDelay:  200,
});

async function runNightlyReport(job: Job): Promise<void> {
  const lockKey = `lock:nightly-report:${job.data.reportDate}`;

  try {
    await using lock = await redlock.acquire([lockKey], 5 * 60 * 1000);  // 5-min lock
    // Only one worker reaches here; others throw and the job is retried later
    await generateReport(job.data.reportDate);
  } catch (err) {
    if (err instanceof ResourceLockedError) {
      logger.info({ jobId: job.id }, 'Report already running — skipping');
      return;   // don't retry; another worker has it
    }
    throw err;
  }
}
```

---

## Scheduled / cron jobs with BullMQ

```ts
// CORRECT — cron job defined at application startup
import { QueueScheduler } from 'bullmq';

// QueueScheduler is required for delayed/recurring jobs
new QueueScheduler('report', { connection: redis });

// Define repeatable job (runs every day at 2 AM UTC)
await reportQueue.add(
  'daily-report',
  { type: 'daily' },
  {
    repeat: { cron: '0 2 * * *', tz: 'UTC' },
    jobId:  'daily-report',   // stable jobId prevents duplicate job registration on restarts
  }
);

// CORRECT — idempotent registration pattern (safe to call on every startup)
const existingJobs = await reportQueue.getRepeatableJobs();
const alreadyRegistered = existingJobs.some((j) => j.name === 'daily-report');
if (!alreadyRegistered) {
  await reportQueue.add('daily-report', { type: 'daily' }, {
    repeat: { cron: '0 2 * * *', tz: 'UTC' },
  });
}
```

---

## Job monitoring with Bull Board

```ts
// CORRECT — expose Bull Board UI in development; behind auth in production
import { createBullBoard } from '@bull-board/api';
import { BullMQAdapter } from '@bull-board/api/bullMQAdapter.js';
import { FastifyAdapter } from '@bull-board/fastify';

const serverAdapter = new FastifyAdapter();
serverAdapter.setBasePath('/admin/queues');

createBullBoard({
  queues: [
    new BullMQAdapter(emailQueue),
    new BullMQAdapter(reportQueue),
  ],
  serverAdapter,
});

// Register behind auth middleware
await fastify.register(serverAdapter.registerPlugin(), { prefix: '/admin/queues' });
// Only accessible to authenticated admins
```

---

## Worker process architecture

```ts
// CORRECT — separate entry point for worker processes (worker.ts)
// In docker-compose.yml or Kubernetes, run as a separate container/deployment:
// command: ["node", "dist/worker.js"]

// worker.ts
import { Worker, QueueEvents } from 'bullmq';
import { redis } from './lib/redis.js';
import { logger } from './lib/logger.js';
import { emailWorkerHandler } from './workers/email.js';
import { reportWorkerHandler } from './workers/report.js';

// Process shutdown gracefully — drain in-flight jobs before exit
const shutdown = async (): Promise<void> => {
  logger.info('Shutting down workers...');
  await emailWorker.close();
  await reportWorker.close();
  await redis.quit();
  process.exit(0);
};

process.on('SIGTERM', shutdown);
process.on('SIGINT',  shutdown);

const emailWorker  = new Worker('email',  emailWorkerHandler,  { connection: redis, concurrency: 5 });
const reportWorker = new Worker('report', reportWorkerHandler, { connection: redis, concurrency: 1 });

logger.info('Workers started');
```
