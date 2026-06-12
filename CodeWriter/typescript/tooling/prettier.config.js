// Prettier config — identical to node/tooling/prettier.config.js so a full-stack
// repo formats the same on both sides. Drop this file into the project root.
// Requires: npm i -D prettier
//
// Run:   npx prettier --check .
// Fix:   npx prettier --write .
//
// Prettier owns formatting; ESLint owns code quality.
// eslint-config-prettier (in eslint.config.js) disables conflicting ESLint rules.

/** @type {import("prettier").Config} */
export default {
  // 100 characters is readable on modern screens while keeping diffs narrow
  printWidth: 100,

  tabWidth: 2,
  useTabs: false,

  // Always write semicolons — omitting them requires remembering ASI edge cases
  semi: true,

  // Single quotes reduce keyboard noise; JSX always gets double quotes
  singleQuote: true,
  jsxSingleQuote: false,

  // ES5 trailing commas: cleaner multi-line diffs, valid in all target environments
  trailingComma: 'es5',

  // Space inside object braces: { foo: 'bar' }
  bracketSpacing: true,

  // Arrow function parens: always — consistent and easier to add a second param
  arrowParens: 'always',

  // LF line endings — prevents CRLF contamination in cross-platform repos
  endOfLine: 'lf',
};
