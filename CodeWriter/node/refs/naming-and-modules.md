# Naming & Modules — Node.js Reference

Grounded in the **Airbnb JavaScript Style Guide**, **Google JavaScript Style Guide**, and the
**Node.js ESM documentation**. ESLint rules `camelcase`, `new-cap`, `import/order`, and
`@typescript-eslint/consistent-type-imports` enforce the conventions below.

---

## Naming conventions

JavaScript has one community standard, not several. Pick these and never deviate.

| Target | Convention | Example |
|---|---|---|
| Variables | `camelCase` | `userId`, `requestCount`, `isAuthenticated` |
| Functions | `camelCase` | `getUserById()`, `parseRequestBody()` |
| Classes | `PascalCase` | `UserService`, `HttpClient`, `AppError` |
| Interfaces / Types / Enums | `PascalCase` | `UserResponse`, `StatusCode`, `RequestOptions` |
| Constants (module-level immutable) | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_TIMEOUT_MS` |
| File names (modules) | `kebab-case` | `user-service.ts`, `parse-token.ts` |
| File names (single-class export) | `PascalCase` | `UserService.ts`, `AppError.ts` |
| Private class fields | `#fieldName` (ES2022) | `#password`, `#cache` |

```ts
// WRONG — wrong case, misleading names, type in name
function GetUserData(UserId: string) { ... }
class userController { ... }
const Users_List: string[] = [];
const strUserName = 'alice';     // type prefix is noise
let _internal = 0;               // underscore "private" is just convention, not enforced
```

```ts
// CORRECT
function getUserData(userId: string) { ... }
class UserController { ... }
const userNames: string[] = [];
const CACHE_TTL_MS = 5 * 60 * 1000;  // module-level constant

class UserService {
  #db: Database;                  // ES2022 private field — truly private
  constructor(db: Database) { this.#db = db; }
}
```

---

## Private fields: `#` not `_`

JavaScript has no "protected" or package-private. The `_prefix` convention is a handshake
agreement that any caller can break. ES2022 private fields (`#`) are enforced by the runtime and
TypeScript — access from outside the class is a hard error at both compile time and runtime.

```ts
// WRONG — anyone can call _connect(); the underscore is a polite request, not enforcement
class DbClient {
  private _connection: Connection | null = null;   // TypeScript-only; no runtime protection
  _connect() { ... }
}
```

```ts
// CORRECT — #connection is physically inaccessible outside the class
class DbClient {
  #connection: Connection | null = null;
  #connect(): void { ... }
  async query(sql: string): Promise<Row[]> {
    if (!this.#connection) await this.#connect();
    return this.#connection!.execute(sql);
  }
}
```

---

## Module system — ESM is mandatory for new code

Node.js 12+ supports ESM natively. The JavaScript ecosystem has standardised on ESM;
`require()` is legacy. Set `"type": "module"` in `package.json` and use `import`/`export`
everywhere.

```json
// package.json
{
  "type": "module",
  "engines": { "node": ">=22" }
}
```

```ts
// WRONG — CommonJS: require(), module.exports, __dirname
const path = require('path');
const { parseId } = require('./utils');
module.exports = { UserService };
const dir = __dirname;
```

```ts
// CORRECT — ESM: import, export, import.meta
import path from 'node:path';
import { parseId } from './utils.js';
export { UserService };
const dir = new URL('.', import.meta.url).pathname;
```

---

## File extensions in ESM imports

Node.js ESM does **not** auto-resolve extensions. You must specify `.js` even when the source
file is `.ts` — TypeScript compiles `.ts` → `.js` and the runtime sees the `.js` file.

```ts
// WRONG — Node.js ESM cannot resolve these at runtime
import { getUser } from './user-service';
import type { Config } from './config';
```

```ts
// CORRECT — explicit .js extension; TypeScript resolves the .ts source
import { getUser } from './user-service.js';
import type { Config } from './config.js';
```

With `moduleResolution: "bundler"` in `tsconfig.json` and `tsx`/`esbuild` as the dev runner,
you may also use `.ts` extensions directly — `tsx` rewrites them. Choose one convention per
project and enforce it via `eslint-plugin-import`.

---

## Named exports over default exports

Default exports break auto-import renaming, make tree-shaking harder, and encourage
one-file-per-entity patterns that fragment the codebase.

```ts
// WRONG — default export; importing as any name is valid, kills discoverability
export default class UserService { ... }
// caller can do: import Foo from './user-service.js'  ← misleading
```

```ts
// CORRECT — named export; import name must match
export class UserService { ... }
export function getUserById(id: string): Promise<User> { ... }

// Only exception: framework entry points that expect a default (e.g. Fastify plugin)
export default fp(plugin);  // fastify-plugin requires default
```

---

## Import ordering

Consistent ordering prevents merge conflicts and aids readability. Three groups, separated by
blank lines, enforced by `eslint-plugin-import`:

1. Node built-ins (prefixed `node:`)
2. Third-party packages
3. First-party (relative imports)

```ts
// WRONG — mixed ordering, missing node: prefix
import { join } from 'path';
import { getUser } from './user-service.js';
import Fastify from 'fastify';
import { readFile } from 'fs/promises';
```

```ts
// CORRECT — three groups, node: prefix on built-ins
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

import Fastify from 'fastify';
import { z } from 'zod';

import { getUserById } from './user-service.js';
import type { AppConfig } from './config.js';
```

---

## CommonJS interop (legacy only)

When a third-party package has no ESM build, use `createRequire` to import it inside an ESM
module. Never revert the whole project to CommonJS for one package.

```ts
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const legacyCjsLib = require('legacy-cjs-only-package');
```

For your own code that must ship both: use `.cjs` extension for CommonJS files and `.mjs`/`.js`
(with `"type": "module"`) for ESM.

---

## Top-level `await`

Permitted in ESM modules (no function wrapper needed). Use it in entry points and config loaders
to delay server start until async setup is complete.

```ts
// WRONG — IIFE wrapper was the only option in CommonJS; unnecessary in ESM
(async () => {
  await db.connect();
  server.listen(3000);
})();
```

```ts
// CORRECT — top-level await in ESM entry point (server.ts)
await db.connect();
await server.listen({ port: env.PORT, host: '0.0.0.0' });
console.log(`Server running on port ${env.PORT}`);
```

Never use top-level `await` in library code — it blocks the module graph and prevents the
library from being used in environments that don't support it.
