// ESLint v9 flat config for React/TypeScript frontends — drop into the project root.
// Requires: npm i -D eslint typescript-eslint @eslint/js eslint-plugin-react
//           eslint-plugin-react-hooks eslint-plugin-jsx-a11y
//           eslint-plugin-testing-library eslint-config-prettier
//
// Run:  npx eslint .
// Fix:  npx eslint . --fix

import js from '@eslint/js';
import ts from 'typescript-eslint';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import testingLibrary from 'eslint-plugin-testing-library';
import prettier from 'eslint-config-prettier';

export default [
  // ── Ignore build output and dependencies ──────────────────────────────────
  { ignores: ['dist', '.next', 'node_modules', 'coverage', '*.config.js', '*.config.ts'] },

  // ── JavaScript baseline ───────────────────────────────────────────────────
  js.configs.recommended,

  // ── TypeScript strict (type-aware) ────────────────────────────────────────
  // strictTypeChecked requires parserOptions.project — remove if you want
  // faster linting without type-aware rules
  ...ts.configs.strictTypeChecked,

  // ── React + hooks + accessibility ─────────────────────────────────────────
  react.configs.flat.recommended,
  react.configs.flat['jsx-runtime'], // automatic JSX runtime — no react/react-in-jsx-scope
  jsxA11y.flatConfigs.recommended,

  // ── Prettier — must be LAST; disables ESLint formatting rules ────────────
  prettier,

  // ── Project-wide custom rules ─────────────────────────────────────────────
  {
    plugins: {
      'react-hooks': reactHooks,
    },

    settings: {
      react: { version: 'detect' },
    },

    rules: {
      // ── Hooks discipline — both are errors, never warnings ────────────────
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',

      // ── React ─────────────────────────────────────────────────────────────
      // TypeScript owns prop validation
      'react/prop-types': 'off',
      // target="_blank" without rel="noreferrer" leaks window.opener
      'react/jsx-no-target-blank': 'error',
      // Components are PascalCase in JSX
      'react/jsx-pascal-case': 'error',
      // Index keys break reconciliation for dynamic lists
      'react/no-array-index-key': 'warn',
      // dangerouslySetInnerHTML is an XSS review point — flag every use
      'react/no-danger': 'warn',

      // ── TypeScript ────────────────────────────────────────────────────────
      // any is a type hole — use unknown at boundaries
      '@typescript-eslint/no-explicit-any': 'error',

      // Floating promises (unawaited mutations, fire-and-forget fetch) are bugs
      '@typescript-eslint/no-floating-promises': 'error',

      // Unused vars with _ prefix escape hatch
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],

      // Enforce import type for type-only imports (required for verbatimModuleSyntax)
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'separate-type-imports' },
      ],

      // Prefer nullish coalescing / optional chaining
      '@typescript-eslint/prefer-nullish-coalescing': 'error',
      '@typescript-eslint/prefer-optional-chain': 'error',

      // ── Security ──────────────────────────────────────────────────────────
      'no-eval': 'error',
      'no-implied-eval': 'error',
    },
  },

  // ── Test files — Testing Library rules + relaxed strictness ──────────────
  {
    files: ['**/*.test.ts', '**/*.test.tsx', '**/*.spec.ts', '**/*.spec.tsx'],
    plugins: { 'testing-library': testingLibrary },
    rules: {
      ...testingLibrary.configs['flat/react'].rules,
      // userEvent simulates real interaction; fireEvent is a low-level escape hatch
      'testing-library/prefer-user-event': 'error',
      'testing-library/no-wait-for-multiple-assertions': 'error',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-floating-promises': 'off',
    },
  },
];
