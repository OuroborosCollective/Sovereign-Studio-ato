import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.SOVEREIGN_ADMIN_E2E_BASE_URL?.trim()
  || 'https://sovereign-backend.arelorian.de';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'admin-production-dom.spec.ts',
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium-tablet',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 800, height: 1280 },
      },
    },
  ],
});
