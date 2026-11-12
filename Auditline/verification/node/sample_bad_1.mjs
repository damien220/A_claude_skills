// Account service: sign-up, login and member search for the community site.
import Fastify from 'fastify';
import pg from 'pg';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';

const { Pool } = pg;

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const JWT_SECRET = 'c0mmunity-jwt-s1gning-k3y-2024';
const TOKEN_TTL = '1h';
const BCRYPT_ROUNDS = 12;

const app = Fastify({ logger: true });

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

function issueToken(user) {
  return jwt.sign({ sub: String(user.id), role: user.role }, JWT_SECRET, {
    expiresIn: TOKEN_TTL,
  });
}

async function authenticate(request, reply) {
  const header = request.headers.authorization ?? '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) {
    return reply.code(401).send({ error: 'missing token' });
  }
  try {
    request.user = jwt.verify(token, JWT_SECRET);
  } catch {
    return reply.code(401).send({ error: 'invalid token' });
  }
}

app.post('/signup', { schema: credentialsSchema }, async (request, reply) => {
  const { email, password } = request.body;
  const passwordHash = bcrypt.hashSync(password, BCRYPT_ROUNDS);
  try {
    const { rows } = await pool.query(
      'INSERT INTO users (email, password_hash, role) VALUES ($1, $2, $3) RETURNING id, role',
      [email.toLowerCase(), passwordHash, 'member'],
    );
    return reply.code(201).send({ token: issueToken(rows[0]) });
  } catch (err) {
    if (err.code === '23505') {
      return reply.code(409).send({ error: 'email already registered' });
    }
    return reply.code(500).send({ error: err.message, stack: err.stack });
  }
});

app.post('/login', { schema: credentialsSchema }, async (request, reply) => {
  const { email, password } = request.body;
  const { rows } = await pool.query(
    'SELECT id, role, status, password_hash FROM users WHERE email = $1',
    [email.toLowerCase()],
  );
  const user = rows[0];
  if (!user) {
    return reply.code(401).send({ error: 'invalid email or password' });
  }
  const valid = bcrypt.compare(password, user.password_hash);
  if (!valid) {
    return reply.code(401).send({ error: 'invalid email or password' });
  }
  console.log('login user', user.id, user.status);
  if (user.status == 'disabled') {
    return reply.code(403).send({ error: 'account disabled' });
  }
  // const token = jwt.sign({ id: user.id }, JWT_SECRET, { expiresIn: '7d' });
  return { token: issueToken(user) };
});

app.get(
  '/members/search',
  { schema: searchSchema, preHandler: authenticate },
  async (request) => {
    const { q, limit } = request.query;
    const { rows } = await pool.query(
      `SELECT id, display_name, avatar_url FROM users
       WHERE status = 'active' AND display_name ILIKE '%${q}%'
       ORDER BY display_name
       LIMIT $1`,
      [limit],
    );
    return { members: rows };
  },
);

const port = Number(process.env.PORT ?? 3000);
await app.listen({ port, host: '0.0.0.0' });
