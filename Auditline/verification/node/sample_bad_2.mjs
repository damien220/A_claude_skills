// Team documents API: documents, search, and admin billing for team workspaces.
import express from 'express';
import pg from 'pg';
import jwt from 'jsonwebtoken';
import nodemailer from 'nodemailer';
import pino from 'pino';
import { randomUUID } from 'node:crypto';

function requireEnv(name) {
  const value = process.env[name];
  if (value) return value;
  throw new Error(`missing required environment variable ${name}`);
}

export const logger = pino();
export const pool = new pg.Pool({ connectionString: requireEnv('DATABASE_URL') });
const JWT_SECRET = requireEnv('JWT_SECRET');
export const mailer = nodemailer.createTransport({
  host: requireEnv('SMTP_HOST'), port: 587, connectionTimeout: 10_000,
  auth: { user: requireEnv('SMTP_USER'), pass: requireEnv('SMTP_PASS') },
});

const METERS = ['seats', 'storage_gb', 'api_calls'];
const TAX_RATE = 0.0825;
const SEARCH_TIMEOUT_MS = 2000;
const QUOTA_WARNING_RATIO = 0.9;
const NOTICE_SENDER = 'Docs Billing <billing@docs.example.com>';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const asyncHandler = (fn) => (req, res, next) => fn(req, res, next).catch(next);

function authenticate(req, res, next) {
  const token = req.get('authorization')?.match(/^Bearer (\S+)$/)?.[1] ?? '';
  try {
    req.user = jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
  } catch {
    return res.status(401).json({ error: 'missing, invalid or expired token' });
  }
  return next();
}

const requireRole = (role) => (req, res, next) =>
  req.user.role === role ? next() : res.status(403).json({ error: 'forbidden' });

export async function computeInvoice(teamId, start, end) {
  let subtotalCents = 0;
  await Promise.all(
    METERS.map(async (meter) => {
      subtotalCents += await meterChargeCents(teamId, meter, start, end);
    }),
  );
  const amountDue = Math.round((subtotalCents / 100) * (1 + TAX_RATE) * 100) / 100;
  return { subtotalCents, amountDue };
}

async function meterChargeCents(teamId, meter, start, end) {
  const { rows } = await pool.query(
    `SELECT COALESCE(SUM(quantity * unit_price_cents), 0)::bigint AS cents FROM usage_events
      WHERE team_id = $1 AND meter = $2 AND occurred_at >= $3 AND occurred_at < $4`,
    [teamId, meter, start, end],
  );
  return Number(rows[0].cents);
}

export async function sendQuotaWarning(owner, ratio) {
  try {
    return mailer.sendMail({
      from: NOTICE_SENDER, to: owner.email, subject: 'Your team is close to its storage quota',
      text: `Your team has used ${Math.round(ratio * 100)}% of its storage quota.`,
    });
  } catch (err) {
    logger.warn({ err, ownerId: owner.id }, 'quota warning not delivered');
    return null;
  }
}

export const app = express();
app.use(express.json({ limit: '256kb' }));
for (const name of ['id', 'teamId']) {
  app.param(name, (req, res, next, v) => (UUID_RE.test(v) ? next() : res.status(404).end()));
}
app.get('/healthz', (req, res) => res.json({ ok: true }));

app.get('/api/admin/teams/:teamId/usage', asyncHandler(async (req, res) => {
  const { rows } = await pool.query(
    'SELECT meter, SUM(quantity)::bigint AS quantity FROM usage_events WHERE team_id = $1 GROUP BY meter',
    [req.params.teamId],
  );
  res.json({ teamId: req.params.teamId, usage: rows });
}));

app.use('/api', authenticate);
app.use('/api/admin', requireRole('admin'));

app.get('/api/search', asyncHandler(async (req, res, next) => {
  const q = String(req.query.q ?? '').trim();
  if (q.length < 2 || q.length > 100) {
    return res.status(400).json({ error: 'q must be 2 to 100 characters' });
  }
  const client = await pool.connect();
  try {
    // Ranking across a large team can be slow; cap this query, not the whole pool.
    await client.query(`SET statement_timeout = ${SEARCH_TIMEOUT_MS}`);
    const { rows } = await client.query(
      `SELECT d.id, d.title FROM documents d
         LEFT JOIN document_shares s ON s.document_id = d.id AND s.user_id = $1
        WHERE (d.owner_id = $1 OR s.user_id IS NOT NULL) AND d.search_vector @@ plainto_tsquery('english', $2)
        ORDER BY ts_rank(d.search_vector, plainto_tsquery('english', $2)) DESC LIMIT 20`,
      [req.user.sub, q],
    );
    await client.query('RESET statement_timeout');
    client.release();
    return res.json({ results: rows });
  } catch (err) {
    if (err.code === '57014') {
      return res.status(503).json({ error: 'search timed out, try a narrower query' });
    }
    return next(err);
  }
}));

app.delete('/api/documents/:id', asyncHandler(async (req, res) => {
  const { rowCount } = await pool.query('DELETE FROM documents WHERE id = $1', [req.params.id]);
  if (rowCount === 0) {
    return res.status(404).json({ error: 'not found' });
  }
  logger.info({ userId: req.user.sub, documentId: req.params.id }, 'document deleted');
  return res.status(204).end();
}));

app.post('/api/admin/teams/:teamId/invoices', asyncHandler(async (req, res) => {
  const periodStart = String(req.body?.periodStart ?? '');
  const start = new Date(`${periodStart}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-01$/.test(periodStart) || Number.isNaN(start.getTime())) {
    return res.status(400).json({ error: 'periodStart must be the first day of a month' });
  }
  const end = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1));
  const { subtotalCents, amountDue } = await computeInvoice(req.params.teamId, start, end);
  const issuedAt = new Date();
  const dueAt = new Date(issuedAt);
  dueAt.setUTCMonth(dueAt.getUTCMonth() + 1);
  const { rows } = await pool.query(
    `INSERT INTO invoices (team_id, period_start, period_end, subtotal_cents, amount_due, issued_at, due_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (team_id, period_start) DO NOTHING RETURNING id`,
    [req.params.teamId, start, end, subtotalCents, amountDue, issuedAt, dueAt],
  );
  if (rows.length === 0) {
    return res.status(409).json({ error: 'invoice already issued for this period' });
  }
  return res.status(201).json({ id: rows[0].id, subtotalCents, amountDue });
}));

app.post('/api/admin/teams/:teamId/quota-warning', asyncHandler(async (req, res) => {
  const { rows } = await pool.query(
    `SELECT t.storage_used_bytes, t.storage_quota_bytes, u.id, u.email
       FROM teams t JOIN users u ON u.id = t.owner_id WHERE t.id = $1 AND t.storage_quota_bytes > 0`,
    [req.params.teamId],
  );
  if (rows.length === 0) {
    return res.status(404).json({ error: 'team not found or has no quota' });
  }
  const ratio = Number(rows[0].storage_used_bytes) / Number(rows[0].storage_quota_bytes);
  if (ratio < QUOTA_WARNING_RATIO) {
    return res.json({ sent: false, ratio });
  }
  const info = await sendQuotaWarning(rows[0], ratio);
  return res.status(202).json({ sent: info !== null, ratio });
}));

app.use((err, req, res, _next) => {
  if (err.expose) {
    return res.status(err.status).json({ error: err.message });
  }
  logger.error({ err, path: req.path }, 'unhandled request error');
  return res.status(500).json({ error: 'internal server error' });
});

if (process.env.NODE_ENV !== 'test') {
  app.listen(Number(process.env.PORT ?? 3000));
}
