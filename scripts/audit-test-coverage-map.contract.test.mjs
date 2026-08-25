import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '..');

describe('test coverage map gate attribution', () => {
  it('attributes verify only to tests under Playwright\'s configured root', () => {
    const playwrightConfig = readFileSync(resolve(root, 'playwright.config.ts'), 'utf8');
    expect(playwrightConfig).toMatch(/testDir:\s*['"]\.\/tests\/e2e['"]/);

    execFileSync(process.execPath, ['scripts/audit-test-coverage-map.mjs', '--json'], {
      cwd: root,
      stdio: 'pipe',
    });

    const report = JSON.parse(
      readFileSync(resolve(root, 'generated/test-coverage-map.json'), 'utf8'),
    );
    const playwrightTests = report.files.filter((entry) => entry.file.startsWith('tests/e2e/'));
    const otherE2ETests = report.files.filter(
      (entry) => entry.category === 'e2e' && !entry.file.startsWith('tests/e2e/'),
    );

    expect(playwrightTests.length).toBeGreaterThan(0);
    expect(otherE2ETests.length).toBeGreaterThan(0);
    for (const entry of playwrightTests) expect(entry.gates).toContain('verify');
    for (const entry of otherE2ETests) expect(entry.gates).not.toContain('verify');

    for (const file of [
      'backend/tests/e2e/oauth-token-never-in-frontend.spec.ts',
      'sovereign-studio-rn/e2e/detox/app.spec.ts',
      'android/app/src/androidTest/java/com/getcapacitor/myapp/ExampleInstrumentedTest.java',
    ]) {
      const entry = report.files.find((candidate) => candidate.file === file);
      expect(entry?.file).toBe(file);
      expect(entry?.gates ?? []).not.toContain('verify');
    }
  });
});
