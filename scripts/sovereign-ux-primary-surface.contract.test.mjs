import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '..');

describe('Sovereign UX primary-surface contract', () => {
  it('accepts the runtime-bound monitor layout and technical inspector together', () => {
    execFileSync(process.execPath, ['scripts/sovereign-ux-contract-scan.mjs'], {
      cwd: root,
      stdio: 'pipe',
      env: { ...process.env, GITHUB_STEP_SUMMARY: '' },
    });

    const report = JSON.parse(
      readFileSync(resolve(root, '.security-reports/sovereign-ux-contract.json'), 'utf8'),
    );
    const layoutCheck = report.checks.find(
      (entry) => entry.id === 'builder:primary-surface-layout-bound',
    );
    const submitCheck = report.checks.find((entry) => entry.id === 'builder:start-visible');

    expect(report.status).toBe('pass');
    expect(layoutCheck?.ok).toBe(true);
    expect(submitCheck?.ok).toBe(true);
  });

  it('guards provider text exactly once before monitor publication', () => {
    const builderSource = readFileSync(
      resolve(root, 'src/features/product/containers/BuilderContainer.tsx'),
      'utf8',
    );

    expect(builderSource.match(/\bcheckChatClaim\(/g) ?? []).toHaveLength(1);
  });
});
