/**
 * builder-container-smoke.spec.ts — Playwright smoke tests for BuilderContainer
 *
 * Verifies real user-visible behavior:
 * 1. App loads with BuilderContainer shell
 * 2. Composer is usable
 * 3. Missing repository evidence is explicit and never claims global readiness
 * 4. Worker state remains unverified until real health or response evidence exists
 * 5. BuilderContainer has proper navigation structure
 *
 * Issue #477
 */
import { test, expect } from '@playwright/test';

// Extended timeout for CI environments where dev server needs more time to start
const EXTENDED_TIMEOUT = { timeout: 30000 };

test.describe('BuilderContainer Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('[data-testid="chat-only-app"]')).toBeVisible(EXTENDED_TIMEOUT);
  });

  test('1. App loads with BuilderContainer shell', async ({ page }) => {
    // Verify the main app container exists
    const appContainer = page.locator('[data-testid="chat-only-app"]');
    await expect(appContainer).toBeVisible();

    // Verify BuilderContainer is rendered
    const builderContainer = page.locator('[data-testid="builder-container"]');
    await expect(builderContainer).toBeVisible();

    // Verify layout attribute is set correctly
    await expect(appContainer).toHaveAttribute('data-layout', 'chat-only-live-entry');

    // Verify ARIA label
    await expect(appContainer).toHaveAttribute('aria-label', 'Sovereign Chat');
  });

  test('2. Composer is usable', async ({ page }) => {
    // Verify composer textarea exists and is enabled
    const composer = page.locator('[data-testid="mission__textarea"]');
    await expect(composer).toBeVisible();
    await expect(composer).toBeEnabled();

    // Verify placeholder text is present
    await expect(composer).toHaveAttribute(
      'placeholder',
      expect.stringContaining('GitHub URL oder Auftrag')
    );

    // Verify we can type into the composer
    await composer.fill('Test mission input');
    await expect(composer).toHaveValue('Test mission input');

    // Clear the input
    await composer.clear();
    await expect(composer).toHaveValue('');
  });

  test('3. Missing repository evidence is explicit and never claims global readiness', async ({ page }) => {
    const repoReason = page.getByText('GitHub-URL direkt im Chat einfügen.');
    await expect(repoReason).toBeVisible();
    await expect(page.getByText('Repo fehlt').first()).toBeVisible();
  });

  test('4. Worker state remains unverified until real evidence exists', async ({ page }) => {
    await expect(page.locator('[data-testid="worker-blocker-card"]')).toHaveCount(0);

    await page.getByRole('button', { name: 'RT – Runtime Quelle' }).click();

    await expect(page.getByText('Cloudflare Worker nicht geprüft')).toBeVisible();
    await expect(
      page.getByText('Noch keine Health- oder Response-Evidence für diese Sitzung.'),
    ).toBeVisible();
  });

  test('5. BuilderContainer has proper navigation structure', async ({ page }) => {
    // Verify the main container is present
    const container = page.locator('[data-testid="builder-container"]');
    await expect(container).toBeVisible();

    // Verify the chat body window is present
    const chatBody = page.locator('[data-testid="sovereign-chat-body-window"]');
    await expect(chatBody).toBeVisible();

    // The app has a clear structure with sovereign summary showing
    const sovereignSummary = page.getByText(/Sovereign/);
    await expect(sovereignSummary.first()).toBeVisible();
  });
});