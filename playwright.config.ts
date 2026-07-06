/**
 * Playwright configuration for Sovereign Studio smoke tests.
 * 
 * These tests verify real user-visible behavior:
 * 1. App loads with BuilderContainer shell
 * 2. Composer is usable
 * 3. Chat intent does not route to OpenHands by default
 * 4. Worker failure shows local runtime diagnostic
 * 
 * Issue #477
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'pnpm run dev',
    url: 'http://localhost:5000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});