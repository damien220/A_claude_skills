// ESLint v9 flat config — drop this file into the project root.
// Requires: npm i -D eslint typescript-eslint @eslint/js eslint-plugin-import
//           eslint-plugin-security eslint-config-prettier
//
// Run:  npx eslint .
// Fix:  npx eslint . --fix

import js from '@eslint/js';
import ts from 'typescript-eslint';
import importPlugin from 'eslint-plugin-import';
import security from 'eslint-plugin-security';
import prettier from 'eslint-config-prettier';

export default [
  // ── Ignore build output and dependencies ──────────────────────────────────
  { ignores: ['dist', 'node_modules', 'coverage', '*.config.js'] },

  // ── JavaScript baseline ───────────────────────────────────────────────────
  js.configs.recommended,

  // ── TypeScript strict (includes recommended + strict + stylistic) ─────────
  // strictTypeChecked requires parserOptions.project — remove if you want
  // faster linting without type-aware rules
  ...ts.configs.strictTypeChecked,

  // ── Security plugin ───────────────────────────────────────────────────────
  security.configs.recommended,

  // ── Prettier — must be LAST; disables ESLint formatting rules ────────────
  prettier,

  // ── Project-wide custom rules ─────────────────────────────────────────────
  {
    plugins: {
      import: importPlugin,
    },

    settings: {
      'import/resolver': {
        typescript: { alwaysTryTypes: true },
        node: { extensions: ['.ts', '.js'] },
      },
    },

    rules: {
      // ── Naming ─────────────────────────────────────────────────────────────
      // camelCase for vars/functions; PascalCase for classes enforced by new-cap
      camelcase: ['error', { properties: 'always', ignoreDestructuring: false }],
      'new-cap': ['error', { newIsCap: true, capIsNew: true }],

      // ── Imports ────────────────────────────────────────────────────────────
      // Groups: node built-ins → external → internal (relative)
      'import/order': [
        'error',
        {
          'newlines-between': 'always',
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          alphabetize: { order: 'asc', caseInsensitive: true },
        },
      ],
      'import/no-extraneous-dependencies': ['error', { devDependencies: ['**/*.test.ts', '**/*.spec.ts'] }],
      'import/no-duplicates': 'error',

      // ── TypeScript ─────────────────────────────────────────────────────────
      // any is a type hole — use unknown at boundaries
      '@typescript-eslint/no-explicit-any': 'error',

      // Floating promises are the most common Node.js async bug
      '@typescript-eslint/no-floating-promises': 'error',

      // Unused vars with _ prefix escape hatch
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],

      // Enforce import type for type-only imports (required for verbatimModuleSyntax)
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports', fixStyle: 'separate-type-imports' }],

      // Explicit return types on public functions (warn, not error, to allow inference on lambdas)
      '@typescript-eslint/explicit-function-return-types': ['warn', {
        allowExpressions: true,
        allowTypedFunctionExpressions: true,
        allowHigherOrderFunctions: true,
      }],

      // Prefer nullish coalescing over || for nullable values
      '@typescript-eslint/prefer-nullish-coalescing': 'error',

      // Prefer optional chaining over && chains
      '@typescript-eslint/prefer-optional-chain': 'error',

      // No unnecessary type assertions
      '@typescript-eslint/no-unnecessary-type-assertion': 'error',

      // ── Security ───────────────────────────────────────────────────────────
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'security/detect-sql-injection': 'error',
      'security/detect-non-literal-regexp': 'warn',
      'security/detect-object-injection': 'warn',
    },
  },

  // ── Test files — relax some rules ─────────────────────────────────────────
  {
    files: ['**/*.test.ts', '**/*.spec.ts', 'tests/**/*.ts'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-floating-promises': 'off',
    },
  },
];
