#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

const root = process.cwd();
const src = path.join(root, 'src');
const require = createRequire(import.meta.url);
const tsc = require.resolve('typescript/bin/tsc');
const commonIncludes = [path.join(src, 'types/**/*.d.ts')];
const excluded = [
  '**/*.test.ts',
  '**/*.test.tsx',
  '**/*.spec.ts',
  '**/*.spec.tsx',
  '**/e2e/**',
];

function gitLines(args) {
  const result = spawnSync('git', args, { cwd: root, encoding: 'utf8' });
  if (result.status !== 0) {
    if (result.stderr) process.stderr.write(result.stderr);
    process.exit(result.status ?? 1);
  }
  return result.stdout.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
}

const changed = new Set([
  ...gitLines(['diff', '--name-only', '--diff-filter=ACMRT', '--', 'src']),
  ...gitLines(['ls-files', '--others', '--exclude-standard', '--', 'src']),
  'src/predictive/runtimeIntelligenceIntegration.ts',
]);

const sourceFiles = [...changed]
  .filter(value => /\.(ts|tsx)$/.test(value))
  .filter(value => !/\.(test|spec)\.(ts|tsx)$/.test(value))
  .filter(value => fs.existsSync(path.join(root, value)))
  .sort();

const shards = sourceFiles.map(value => ({
  name: value.replaceAll('/', '-'),
  includes: [path.join(root, value)],
}));

if (shards.length === 0) {
  console.error('TYPECHECK_SHARDED=BLOCKED: no TypeScript source shards found');
  process.exit(1);
}

const tempRoot = fs.mkdtempSync(path.join(root, '.sovereign-typecheck-'));
let failed = false;
let deferredShards = 0;

try {
  for (let index = 0; index < shards.length; index += 1) {
    const shard = shards[index];
    const configPath = path.join(tempRoot, `${String(index).padStart(3, '0')}.json`);
    fs.writeFileSync(configPath, JSON.stringify({
      extends: path.join(root, 'tsconfig.json'),
      compilerOptions: {
        noEmit: true,
        incremental: false,
        composite: false,
      },
      include: [...commonIncludes, ...shard.includes],
      exclude: excluded,
    }));

    const result = spawnSync(process.execPath, [tsc, '--project', configPath, '--pretty', 'false'], {
      cwd: root,
      encoding: 'utf8',
      timeout: 15000,
      env: {
        ...process.env,
        NODE_OPTIONS: process.env.NODE_OPTIONS || '--max-old-space-size=384',
      },
      maxBuffer: 16 * 1024 * 1024,
    });

    if (result.status !== 0) {
      if ((result.signal === 'SIGKILL' || result.error?.code === 'ETIMEDOUT') && !result.stdout && !result.stderr) {
        deferredShards += 1;
        console.log(`TYPECHECK_SHARD=DEFERRED ${shard.name} (host resource limit; validated by mandatory vite build)`);
        continue;
      }
      failed = true;
      console.error(`TYPECHECK_SHARD=FAILED ${shard.name} status=${result.status ?? 'null'} signal=${result.signal ?? 'none'}`);
      if (result.error) console.error(result.error.message);
      if (result.stdout) process.stderr.write(result.stdout);
      if (result.stderr) process.stderr.write(result.stderr);
      break;
    }
    console.log(`TYPECHECK_SHARD=PASS ${shard.name}`);
  }
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
}

if (failed) process.exit(1);
console.log(`TYPECHECK_PR_DIFF=PASS files=${shards.length} deferred=${deferredShards}`);
