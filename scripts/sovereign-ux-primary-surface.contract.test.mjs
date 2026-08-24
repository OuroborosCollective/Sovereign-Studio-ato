import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '..');

describe('Sovereign UX primary-surface contract', () => {
  it('accepts the runtime-bound monitor layout and chat fallback together', () => {
    execFileSync(process.execPath, ['scripts/sovereign-ux-contract-scan.mjs'], {
      cwd: root,
      stdio: 'pipe',
      env: { ...process.env, GITHUB_STEP_SUMMARY: '' },
    });

    const report = JSON.parse(
      readFileSync(resolve(root, '.security-reports/sovereign-ux-contract.json'), 'utf8'),
    );
    const check = report.checks.find((entry) => entry.id === 'builder:primary-surface-layout-bound');

    expect(report.status).toBe('pass');
    expect(check?.ok).toBe(true);
  });
});
