import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const source = readFileSync(join(__dirname, 'run-e2e.ts'), 'utf8');

describe('E2E runner command contract', () => {
  it('uses the current Jest CLI path pattern flag', () => {
    expect(source).toContain('--testPathPatterns');
    expect(source).not.toMatch(/--testPathPattern[^s]/);
  });

  it('does not install Jest dynamically through npx in CI', () => {
    expect(source).toContain("await this.runCommand('pnpm'");
    expect(source).not.toContain("await this.runCommand('npx'");
  });

  it('reports missing optional suites as skipped instead of fake-passing them', () => {
    expect(source).toContain("status: 'skipped'");
    expect(source).toContain('recordSkipped');
    expect(source).toContain('SKIPPED');
  });

  it('skips Detox when the config exists but the dependency is not installed', () => {
    expect(source).toContain('packageJsonHasDependency');
    expect(source).toContain("packageJsonHasDependency(rootPackage, 'detox')");
    expect(source).toContain("packageJsonHasDependency(rnPackage, 'detox')");
    expect(source).toContain('Detox config found, but detox is not installed in package dependencies.');
  });
});
