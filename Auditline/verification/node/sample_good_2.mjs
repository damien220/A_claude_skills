// PayStream webhook receiver: verifies signed payment events and records them against orders.
import express from 'express';
import pg from 'pg';
import pino from 'pino';
import { createHmac, timingSafeEqual } from 'node:crypto';

function requireEnv(name) {
  const value = process.env[name];
  if (value) return value;
  throw new Error(`missing required environment variable ${name}`);
}

const logger = pino();
const pool = new pg.Pool({
  connectionString: requireEnv('DATABASE_URL'),
  connectionTimeoutMillis: 5_000,
  statement_timeout: 10_000,
});
const WEBHOOK_SECRET = requireEnv('PAYSTREAM_WEBHOOK_SECRET');
// Our public merchant id; PayStream includes it on every event sent to this account.
const MERCHANT_ID = 'mch_4Jt9QbW2xLr7';
const SIGNATURE_HEADER = 'paystream-signature';
const TOLERANCE_SECONDS = 300;
const PURGE_INTERVAL_MS = 60 * 60 * 1000;
const PURGE_BATCH = 1000;

// Each handled event type stamps exactly one timestamp column on the order.
const STATUS_COLUMNS = Object.freeze({
  'payment.succeeded': 'paid_at',
  'payment.failed': 'payment_failed_at',
  'payment.refunded': 'refunded_at',
});

export function verifySignature(rawBody, header, nowSeconds) {
  const match = /^t=(\d{1,12}),v1=([0-9a-f]{64})$/.exec(header ?? '');
  if (!match) return false;
  const timestamp = Number(match[1]);
  if (Math.abs(nowSeconds - timestamp) > TOLERANCE_SECONDS) return false;
  const expected = createHmac('sha256', WEBHOOK_SECRET)
    .update(`${match[1]}.`)
    .update(rawBody)
    .digest();
  const received = Buffer.from(match[2], 'hex');
  return received.length === expected.length && timingSafeEqual(received, expected);
}

export function parseEvent(rawBody) {
  let event;
  try {
    event = JSON.parse(rawBody.toString('utf8'));
  } catch {
    return null;
  }
  const valid =
    typeof event?.id === 'string' && event.id.length <= 64 &&
    typeof event.type === 'string' &&
    event.merchant === MERCHANT_ID &&
    Number.isSafeInteger(event.created) &&
    typeof event.data?.orderId === 'string' && event.data.orderId.length <= 64 &&
    Number.isSafeInteger(event.data.amountCents) && event.data.amountCents >= 0;
  return valid ? event : null;
}

async function applyEvent(event) {
  const column = STATUS_COLUMNS[event.type];
  const occurredAt = new Date(event.created * 1000);
  const client = await pool.connect();
  let discard = false;
  try {
    await client.query('BEGIN');
    const seen = await client.query(
      'INSERT INTO webhook_events (id, type, received_at) VALUES ($1, $2, now()) ON CONFLICT (id) DO NOTHING',
      [event.id, event.type],
    );
    if (seen.rowCount === 0) {
      await client.query('ROLLBACK');
      return 'duplicate';
    }
    const { rows } = await client.query(
      `UPDATE orders SET ${column} = $2 WHERE public_id = $1 RETURNING id`,
      [event.data.orderId, occurredAt],
    );
    const orderId = rows[0]?.id;
    if (orderId !== undefined) {
      await client.query(
        `INSERT INTO payment_records (order_id, event_id, kind, amount_cents, occurred_at)
         VALUES ($1, $2, $3, $4, $5)`,
        [orderId, event.id, event.type, event.data.amountCents, occurredAt],
      );
    }
    // A worker drains this outbox, so a slow fulfillment service never delays the ack.
    if (orderId !== undefined && event.type === 'payment.succeeded') {
      await client.query(
        'INSERT INTO fulfillment_outbox (order_id, event_id) VALUES ($1, $2)',
        [orderId, event.id],
      );
    }
    await client.query('COMMIT');
    return orderId === undefined ? 'unknown-order' : 'applied';
  } catch (err) {
    await client.query('ROLLBACK').catch((rollbackErr) => {
      discard = true;
      logger.error({ err: rollbackErr }, 'rollback failed, discarding connection');
    });
    throw err;
  } finally {
    client.release(discard);
  }
}

export async function purgeOldEvents() {
  // Batches run in sequence so each DELETE holds its locks briefly.
  for (;;) {
    const { rowCount } = await pool.query(
      `DELETE FROM webhook_events WHERE id IN (
         SELECT id FROM webhook_events WHERE received_at < now() - interval '30 days' LIMIT $1)`,
      [PURGE_BATCH],
    );
    if (rowCount < PURGE_BATCH) return;
  }
}

const asyncHandler = (fn) => (req, res, next) => fn(req, res, next).catch(next);

export const app = express();

app.post(
  '/webhooks/paystream',
  express.raw({ type: 'application/json', limit: '64kb' }),
  asyncHandler(async (req, res) => {
    const nowSeconds = Math.floor(Date.now() / 1000);
    if (!Buffer.isBuffer(req.body) || !verifySignature(req.body, req.get(SIGNATURE_HEADER), nowSeconds)) {
      return res.status(401).json({ error: 'invalid signature' });
    }
    const event = parseEvent(req.body);
    if (!event) {
      return res.status(400).json({ error: 'malformed event' });
    }
    if (!Object.hasOwn(STATUS_COLUMNS, event.type)) {
      return res.status(202).json({ ignored: event.type });
    }
    const outcome = await applyEvent(event);
    const level = outcome === 'unknown-order' ? 'warn' : 'info';
    logger[level]({ eventId: event.id, type: event.type, outcome }, 'payment event handled');
    return res.status(200).json({ received: true, outcome });
  }),
);

app.use((err, req, res, _next) => {
  if (err.expose) {
    return res.status(err.status).json({ error: err.message });
  }
  logger.error({ err, path: req.path }, 'unhandled request error');
  return res.status(500).json({ error: 'internal server error' });
});

function schedulePurge() {
  setTimeout(async () => {
    try {
      await purgeOldEvents();
    } catch (err) {
      logger.error({ err }, 'webhook event purge failed');
    }
    schedulePurge();
  }, PURGE_INTERVAL_MS).unref();
}

if (process.env.NODE_ENV !== 'test') {
  const server = app.listen(Number(process.env.PORT ?? 3000));
  schedulePurge();
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.once(signal, () => server.close(() => pool.end()));
  }
}
