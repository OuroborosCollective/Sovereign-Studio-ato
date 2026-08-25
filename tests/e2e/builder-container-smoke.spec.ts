/**
 * builder-container-smoke.spec.ts — Playwright smoke tests for BuilderContainer
 *
 * Verifies real user-visible behavior:
 * 1. App loads with BuilderContainer shell
 * 2. Monitor communication dock is usable
 * 3. Missing repository evidence is explicit and never claims global readiness
 * 4. LLM runtime remains unverified until real response evidence exists
 * 5. Monitor/Desktop is the permanent primary navigation surface
 *
 * Issue #477
 */
import { test, expect } from '@playwright/test';

// Extended timeout for CI environments where dev server needs more time to start
const EXTENDED_TIMEOUT = { timeout: 30000 };

test.describe('BuilderContainer Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('[data-testid="sovereign-monitor-app"]')).toBeVisible(EXTENDED_TIMEOUT);
  });

  test('1. App loads with BuilderContainer shell', async ({ page }) => {
    // Verify the main app container exists
    const appContainer = page.locator('[data-testid="sovereign-monitor-app"]');
    await expect(appContainer).toBeVisible();

    // Verify BuilderContainer is rendered
    const builderContainer = page.locator('[data-testid="builder-container"]');
    await expect(builderContainer).toBeVisible();

    // Verify layout attribute is set correctly
    await expect(appContainer).toHaveAttribute('data-layout', 'monitor-first-live-workspace');

    // Verify ARIA label and permanent monitor surface
    await expect(appContainer).toHaveAttribute('aria-label', 'Sovereign Workspace Monitor');
    await expect(page.locator('[data-testid="sovereign-live-monitor-primary"]')).toBeVisible();
    await expect(page.locator('[data-testid="live-workspace-monitor-desktop"]')).toBeVisible();
  });

  test('2. Monitor communication dock is usable', async ({ page }) => {
    const composer = page.getByLabel('Frage an Sovereign während Live Monitor');
    await expect(composer).toBeVisible();
    await expect(composer).toBeEnabled();
    await expect(composer).toHaveAttribute(
      'placeholder',
      expect.stringContaining('ohne den Monitor zu verlassen')
    );
    await composer.fill('Test mission input');
    await expect(composer).toHaveValue('Test mission input');
    await composer.clear();
    await expect(composer).toHaveValue('');
    await expect(page.locator('[data-testid="sovereign-chat-body-window"]')).toHaveCount(0);
  });

  test('3. Missing repository evidence stays explicit in the monitor and never claims readiness', async ({ page }) => {
    await expect(page.getByText('Repo fehlt').first()).toBeVisible();
    await expect(page.getByText('Noch kein Repository an den Workspace-Monitor gebunden.')).toHaveCount(0);
  });

  test('4. LLM runtime remains unverified until real evidence exists', async ({ page }) => {
    await expect(page.locator('[data-testid="worker-blocker-card"]')).toHaveCount(0);

    await page.getByRole('button', { name: 'RT – Runtime Quelle' }).click();

    await expect(page.getByText('LLM Runtime nicht geprüft')).toBeVisible();
    await expect(
      page.getByText('Noch keine Health- oder Response-Evidence für diese Sitzung.'),
    ).toBeVisible();
  });

  test('5. Monitor/Desktop remains primary while Inspector is only secondary', async ({ page }) => {
    const container = page.locator('[data-testid="builder-container"]');
    await expect(container).toBeVisible();
    await expect(page.getByRole('button', { name: 'Live Monitor' })).toBeVisible();
    await expect(page.locator('[data-testid="live-workspace-monitor"]')).toBeVisible();
    await expect(page.locator('[data-testid="live-workspace-monitor-desktop"]')).toBeVisible();
    await expect(page.locator('[data-testid="monitor-communication-dock"]')).toBeVisible();
    await expect(page.locator('[data-testid="sovereign-chat-body-window"]')).toHaveCount(0);
  });
});