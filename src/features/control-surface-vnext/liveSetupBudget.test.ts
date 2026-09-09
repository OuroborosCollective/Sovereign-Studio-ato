import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('protected live setup has a bounded lifecycle budget, not a proof bypass', () => {
  it('changes only the live suite default while preserving ordinary smoke timeout', () => {
    const config = readFileSync('playwright.config.ts', 'utf8');
    expect(config).toContain('timeout: liveFivePath ? 120_000 : 30_000');
    expect(config).toContain('retries: liveFivePath ? 0 : (process.env.CI ? 2 : 0)');
    expect(config).toContain('ignoreHTTPSErrors: false');
  });
  it('still requires all five real independently verified Draft PRs', () => {
    const source = readFileSync('tests/e2e/five-draft-pr-paths.spec.ts', 'utf8');
    expect(source).toContain('if (evidence.length !== 5)');
    expect(source).toContain('requireVerifiedSessionIdentity(session.status()');
    expect(source).toContain('await verifyReadmeAtHead(');
    expect(source).toContain('return verifyOwnedDraftCleanup(');
  });
});
