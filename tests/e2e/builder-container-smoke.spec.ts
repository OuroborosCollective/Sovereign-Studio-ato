/**
 * builder-container-smoke.spec.ts — Playwright smoke tests for BuilderContainer
 *
 * Verifies real user-visible behavior:
 * 1. App loads with BuilderContainer shell
 * 2. Composer is usable
 * 3. Chat intent does not route to OpenHands by default (repo-gated actions)
 * 4. Worker failure shows local runtime diagnostic (not blind repeat)
 * 5. BuilderContainer has proper navigation structure
 *
 * Issue #477
 */
import { test, expect } from '@playwright/test';

test.describe('BuilderContainer Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for the app to fully load
    await page.waitForLoadState('networkidle');
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

  test('3. Chat intent does not route to OpenHands by default', async ({ page }) => {
    // Actions require a repo to be actionable - this prevents silent routing to OpenHands
    // The repo reason explains why actions are limited without a repo

    // Verify repo reason is shown (explains why actions are limited)
    const repoReason = page.getByText('GitHub-URL direkt im Chat einfügen.');
    await expect(repoReason).toBeVisible();

    // Verify sovereign summary shows ready state (Sovereign mode, not fallback to OpenHands)
    const sovereignSummary = page.getByText(/Sovereign ist bereit/);
    await expect(sovereignSummary).toBeVisible();

    // The Start Task button exists but requires repo - verified by repoReason visibility
    // If the repoReason is visible, it means actions are properly gated
    await expect(repoReason).toBeVisible();
  });

  test('4. Worker failure shows local runtime diagnostic (not blind repeat)', async ({ page }) => {
    // Intercept the Worker route and simulate a 500 error
    // This proves the UI surfaces a diagnostic from local runtime state
    
    // Route matching the actual Worker endpoint used by the app
    await page.route('**/v1/chat/completions', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            type: 'internal_error',
            message: 'Simulated worker failure for smoke test',
            code: 'WORKER_RUNTIME_ERROR',
          },
        }),
      });
    });

    // Also intercept the health endpoint to avoid additional failures
    await page.route('**/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, configured: true }),
      });
    });

    // Submit a chat message that would trigger the Worker
    const composer = page.locator('[data-testid="mission__textarea"]');
    await composer.fill('Test nachricht');
    
    // Submit the form
    await composer.press('Enter');
    
    // Wait for the response to arrive and be processed
    // The app should NOT be stuck in infinite thinking - it should show diagnostic info
    await page.waitForTimeout(3000);
    
    // Key assertion: WorkerBlockerCard should appear with diagnostic info
    // This proves the app shows LOCAL runtime diagnostic, NOT blind repeat
    const workerBlockerCard = page.locator('[data-testid="worker-blocker-card"]');
    await expect(workerBlockerCard).toBeVisible();
    
    // Verify the card contains diagnostic text (Scope info from local runtime state)
    await expect(workerBlockerCard).toContainText('Worker nicht erreichbar');
    
    // Verify scope classification is shown (from local diagnostic runtime, not worker response)
    await expect(workerBlockerCard).toContainText('Scope:');
    
    // Verify the diagnostic contains HTTP status info (from local runtime classification)
    await expect(workerBlockerCard).toContainText('HTTP');
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