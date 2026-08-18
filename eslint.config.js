// ESLint flat config (ESLint v9).
//
// The repository ships `eslint .` as the `lint` script but previously had no
// config, so the gate always failed with "couldn't find an eslint.config file".
//
// Scope: this config lints the JavaScript surface of the repository
// (*.js, *.mjs, *.cjs) using ESLint's built-in espree parser. TypeScript
// (*.ts, *.tsx) is intentionally ignored: linting TypeScript requires the
// typescript-eslint parser/plugin, which is a separate, larger effort. Until
// that lands, the `lint` gate is real and passing on the JS surface rather than
// crashing on startup.
//
// Auxiliary subprojects (React Native app, launch-bot, mesh-system, MCP tools)
// that may carry their own conventions or TypeScript-in-.js files are excluded.

// Minimal globals for Node and browser. Inlined (rather than importing the
// `globals` package) so this config adds no new dependencies or lockfile
// changes. Only the names actually used by the linted JS surface are needed.
const commonGlobals = {
  // Node
  process: "readonly",
  module: "readonly",
  require: "readonly",
  exports: "readonly",
  __dirname: "readonly",
  __filename: "readonly",
  console: "readonly",
  Buffer: "readonly",
  global: "readonly",
  setTimeout: "readonly",
  clearTimeout: "readonly",
  setInterval: "readonly",
  clearInterval: "readonly",
  setImmediate: "readonly",
  queueMicrotask: "readonly",
  URL: "readonly",
  URLSearchParams: "readonly",
  TextEncoder: "readonly",
  TextDecoder: "readonly",
  fetch: "readonly",
  // Browser (some scripts run in build/browser context)
  window: "readonly",
  document: "readonly",
  navigator: "readonly",
  localStorage: "readonly",
};

const ignoredDirs = [
  "node_modules/**",
  "dist/**",
  "build/**",
  "android/app/src/main/assets/public/**",
  "coverage/**",
  "sovereign-studio-rn/**",
  "cloudflare-worker/**",
  "cloudflare-worker-ai-proxy/**",
  "launch-bot-v1/**",
  "mesh-system/**",
  "tools/**",
  ".git/**",
];

export default [
  {
    ignores: ignoredDirs,
  },
  {
    files: ["**/*.js", "**/*.mjs", "**/*.cjs"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: commonGlobals,
    },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "no-unreachable": "warn",
      "no-constant-condition": "warn",
      "no-debugger": "warn",
    },
  },
];
