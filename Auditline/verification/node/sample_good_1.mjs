// Account service: sign-up, login and member search for the community site.
import Fastify from 'fastify';
import helmet from '@fastify/helmet';
import pg from 'pg';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';

const { Pool } = pg;

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`missing required environment variable ${name}`);
  }
  return value;
}

const pool = new Pool({ connectionString: requireEnv('DATABASE_URL') });
const JWT_SECRET = requireEnv('JWT_SECRET');
const TOKEN_TTL = '1h';
const BCRYPT_ROUNDS = 12;
// Compared against when the email is unknown, so both paths take the same time.
const DUMMY_HASH = await bcrypt.hash('not-a-real-password', BCRYPT_ROUNDS);

const app = Fastify({
  logger: { redact: ['req.headers.authorization'] },
});
await app.register(helmet);

const credentialsSchema = {
  body: {
    type: 'object',
    required: ['email', 'password'],
    additionalProperties: false,
    properties: {
      email: { type: 'string', format: 'email', maxLength: 254 },
      password: { type: 'string', minLength: 12, maxLength: 128 },
    },
  },
};

const searchSchema = {
  querystring: {
    type: 'object',
    required: ['q'],
    properties: {
      q: { type: 'string', minLength: 2, maxLength: 64 },
      limit: { type: 'integer', minimum: 1, maximum: 50, default: 20 },
    },
  },
};

function problem(reply, status, title) {
  return reply
    .code(status)
    .type('application/problem+json')
    .send({ type: 'about:blank', title, status });
}

function issueToken(user) {
  return jwt.sign({ sub: String(user.id), role: user.role }, JWT_SECRET, {
    algorithm: 'HS256',
    expiresIn: TOKEN_TTL,
  });
}

async function authenticate(request, reply) {
  const header = request.headers.authorization ?? '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) {
    return problem(reply, 401, 'missing bearer token');
  }
  try {
    request.user = jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
  } catch {
    return problem(reply, 401, 'invalid or expired token');
  }
}

app.setErrorHandler((err, request, reply) => {
  if (err.validation) {
    return problem(reply, 400, err.message);
  }
  request.log.error({ err }, 'unhandled request error');
  return problem(reply, 500, 'internal server error');
});

app.post('/signup', { schema: credentialsSchema }, async (request, reply) => {
  const { email, password } = request.body;
  const passwordHash = await bcrypt.hash(password, BCRYPT_ROUNDS);
  try {
    const { rows } = await pool.query(
      'INSERT INTO users (email, password_hash, role) VALUES ($1, $2, $3) RETURNING id, role',
      [email.toLowerCase(), passwordHash, 'member'],
    );
    return reply.code(201).send({ token: issueToken(rows[0]) });
  } catch (err) {
    if (err.code === '23505') {
      return problem(reply, 409, 'email already registered');
    }
    throw err;
  }
});

app.post('/login', { schema: credentialsSchema }, async (request, reply) => {
  const { email, password } = request.body;
  const { rows } = await pool.query(
    'SELECT id, role, status, password_hash FROM users WHERE email = $1',
    [email.toLowerCase()],
  );
  const user = rows[0];
  const valid = await bcrypt.compare(password, user?.password_hash ?? DUMMY_HASH);
  if (!user || !valid) {
    return problem(reply, 401, 'invalid email or password');
  }
  if (user.status === 'disabled') {
    return problem(reply, 403, 'account disabled');
  }
  request.log.info({ userId: user.id }, 'login succeeded');
  return { token: issueToken(user) };
});

app.get(
  '/members/search',
  { schema: searchSchema, preHandler: authenticate },
  async (request) => {
    const { q, limit } = request.query;
    const pattern = `%${q.replace(/[\\%_]/g, '\\$&')}%`;
    const { rows } = await pool.query(
      `SELECT id, display_name, avatar_url FROM users
       WHERE status = 'active' AND display_name ILIKE $1
       ORDER BY display_name
       LIMIT $2`,
      [pattern, limit],
    );
    return { members: rows };
  },
);

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, async () => {
    await app.close();
    await pool.end();
    process.exit(0);
  });
}

const port = Number(process.env.PORT ?? 3000);
await app.listen({ port, host: '0.0.0.0' });
