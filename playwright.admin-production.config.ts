import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'admin-production-dom.spec.ts',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  timeout: 120_000,
  expect: {
    timeout: 20_000,
  },
  use: {
    ...devices['Desktop Chrome'],
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report/admin-production' }]],
});
