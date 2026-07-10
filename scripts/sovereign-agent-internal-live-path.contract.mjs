#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve(import.meta.dirname, '..');
const retired = ['open', 'hands'].join('');
const forbidden = new RegExp(`${retired}|VITE_${retired.toUpperCase()}|${retired.toUpperCase()}_API_URL|external-agent-runtime`, 'i');
const liveRoots = ['src', 'backend/agent_runtime', 'scripts/sovereign-backend/agent_runtime'];
function walk(entry) {
  const target = path.join(root, entry);
  if (!fs.existsSync(target)) return [];
  if (fs.statSync(target).isFile()) return [target];
  return fs.readdirSync(target, { withFileTypes: true }).flatMap((item) => walk(path.join(entry, item.name)));
}
function read(name) { return fs.readFileSync(path.join(root, name), 'utf8'); }

test('live product source contains no retired executor imports, env or routes', () => {
  const offenders = liveRoots.flatMap(walk)
    .filter((file) => /\.(?:ts|tsx|js|jsx|mjs|py)$/.test(file))
    .filter((file) => !file.endsWith('sovereign-agent-internal-live-path.contract.mjs'))
    .filter((file) => forbidden.test(fs.readFileSync(file, 'utf8')));
  assert.deepEqual(offenders.map((file) => path.relative(root, file)), []);
});

test('frontend client is internal-route-only', () => {
  const client = read('src/features/product/runtime/sovereignAgentClient.ts');
  const runtime = read('src/features/product/runtime/sovereignAgentRuntime.ts');
  assert.match(client, /\/api\/user\/agent\/jobs/);
  assert.doesNotMatch(client, /['"`]\/jobs/);
  assert.match(runtime, /executor: 'sovereign-local-runner'/);
  assert.doesNotMatch(runtime, /external-agent-runtime/);
});

test('database and deploy path enforce internal, fail-closed migrations', () => {
  const executorMigration = read('scripts/sovereign-backend/migrations/007_sovereign_agent_internal_executor_only.sql');
  assert.match(executorMigration, /CHECK \(executor = 'sovereign-local-runner'\)/);

  const bootstrap = read('scripts/sovereign-backend/migrations/000_backend_bootstrap_schema.sql');
  for (const table of [
    'admin_api_keys',
    'credit_ledger',
    'payment_methods',
    'credit_packages',
    'llm_routes',
    'launcher_overrides',
    'toolchain_tools',
    'audit_log',
    'user_skills',
    'transactions',
    'schema_migrations',
  ]) {
    assert.match(bootstrap, new RegExp(`CREATE TABLE IF NOT EXISTS ${table}\\b`), table);
  }
  assert.match(bootstrap, /WHERE NOT EXISTS[\s\S]*credit_packages/);

  const dockerfile = read('scripts/sovereign-backend/Dockerfile');
  assert.match(dockerfile, /COPY migrations/);
  const migrate = read('scripts/sovereign-backend/auto-migrate.sh');
  assert.match(migrate, /ON_ERROR_STOP=1/);
  assert.match(migrate, /find "\$\{MIGRATION_DIR\}"[\s\S]*\| sort/);
  assert.match(migrate, /No SQL migrations found/);
  assert.match(migrate, /no matching bootstrap key could be persisted/);
  assert.doesNotMatch(migrate, /\|\|\s*true/);
});

test('deployed runtime mirrors the canonical backend runtime', () => {
  const files = (base) => walk(base).filter((file) => file.endsWith('.py')).map((file) => path.relative(path.join(root, base), file)).sort();
  const canonical = files('backend/agent_runtime');
  const deployed = files('scripts/sovereign-backend/agent_runtime');
  assert.deepEqual(deployed, canonical);
  for (const relative of canonical) assert.equal(read(path.join('scripts/sovereign-backend/agent_runtime', relative)), read(path.join('backend/agent_runtime', relative)), relative);
});
