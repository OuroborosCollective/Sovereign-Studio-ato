import { test, expect } from '@playwright/test';

const EXTENDED_TIMEOUT = { timeout: 30_000 };

test.describe('Play release chat browser smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('[data-testid="sovereign-release-chat"]')).toBeVisible(EXTENDED_TIMEOUT);
  });

  test('1. App loads the focused Play chat surface', async ({ page }) => {
    const app = page.locator('[data-testid="sovereign-release-chat"]');
    await expect(app).toHaveAttribute('data-layout', 'play-release-chat');
    await expect(app).toHaveAttribute('aria-label', 'Sovereign Chat');
    await expect(page.getByText('Was möchtest du wissen oder erledigen?')).toBeVisible();
    await expect(page.locator('[data-testid="sovereign-monitor-app"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="live-workspace-monitor"]')).toHaveCount(0);
  });

  test('2. Email/password login is reachable and external OAuth controls are absent from the login dialog', async ({ page }) => {
    await page.getByRole('button', { name: 'Anmelden', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Anmelden' });
    await expect(dialog.locator('input[type="email"]')).toBeVisible();
    await expect(dialog.locator('input[type="password"]')).toBeVisible();
    await expect(dialog.getByText(/Google/i)).toHaveCount(0);
    await expect(dialog.getByText(/GitHub/i)).toHaveCount(0);
    await expect(dialog.getByText(/Passkey/i)).toHaveCount(0);
    await expect(dialog.getByText(/Account-Key/i)).toHaveCount(0);
  });

  test('3. Chat composer is present but requires an authenticated session', async ({ page }) => {
    const composer = page.getByLabel('Nachricht an Sovereign');
    await expect(composer).toBeVisible();
    await expect(composer).toHaveAttribute('placeholder', 'Zum Chatten bitte anmelden…');
    await expect(page.getByRole('button', { name: /Senden/i })).toBeDisabled();
  });

  test('4. Release root does not expose unfinished monitor controls', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Live Monitor' })).toHaveCount(0);
    await expect(page.locator('[data-testid="monitor-communication-dock"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="live-workspace-monitor-desktop"]')).toHaveCount(0);
  });

  test('5. Release shell remains responsive at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.locator('[data-testid="sovereign-release-chat"]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Anmelden', exact: true })).toBeVisible();
    await expect(page.getByLabel('Nachricht an Sovereign')).toBeVisible();
  });
});
