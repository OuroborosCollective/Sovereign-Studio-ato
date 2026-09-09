/**
 * Playwright configuration for Sovereign Studio browser evidence.
 *
 * The default suite verifies the shipped vNext control surface, its authenticated
 * backend boundary, runtime projections and publication gates. The live five-path
 * lane remains separately opt-in because it performs real repository effects.
 */
import { defineConfig, devices } from '@playwright/test';

const liveFivePath = process.env.SOVEREIGN_E2E_LIVE === '1';
const appUrl = process.env.SOVEREIGN_E2E_APP_URL?.trim() || 'http://localhost:3000';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: !liveFivePath,
  forbidOnly: !!process.env.CI,
  retries: liveFivePath ? 0 : (process.env.CI ? 2 : 0),
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [['line'], ['html', { open: 'never', outputFolder: 'playwright-report' }]]
    : [['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: appUrl,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: liveFivePath
      ? 'node ./node_modules/vite/bin/vite.js preview --port 3000 --host 127.0.0.1'
      : 'node ./node_modules/vite/bin/vite.js preview --port 3000 --host 0.0.0.0',
    url: appUrl,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
