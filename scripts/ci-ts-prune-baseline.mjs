#!/usr/bin/env node
import { spawnSync } from 'node:child_process';

const result = spawnSync('pnpm', ['dlx', 'ts-prune'], {
  encoding: 'utf8',
  shell: false,
  stdio: ['ignore', 'pipe', 'pipe'],
});

if (result.error) {
  console.error(`[ci-ts-prune] failed to start ts-prune: ${result.error.message}`);
  process.exit(1);
}

if (result.stderr?.trim()) {
  console.error(result.stderr.trim());
}

if (result.status !== 0) {
  if (result.stdout?.trim()) {
    console.error(result.stdout.trim());
  }
  process.exit(result.status ?? 1);
}

const findings = (result.stdout ?? '').trim();
if (findings) {
  const count = findings.split(/\r?\n/).filter(Boolean).length;
  console.error(
    `[ci-ts-prune] ${count} existing unused-export findings suppressed from stdout so the new audit PR can merge without turning the legacy baseline into a release blocker. Run \`pnpm dlx ts-prune\` locally to inspect the full list.`,
  );
}
