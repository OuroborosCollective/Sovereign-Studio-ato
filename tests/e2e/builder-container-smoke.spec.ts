import { test, expect } from '@playwright/test';

const EXTENDED_TIMEOUT = { timeout: 30_000 };

test.describe('Monitor-first workspace browser smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('[data-testid="sovereign-monitor-app"]')).toBeVisible(EXTENDED_TIMEOUT);
  });

  test('1. App loads the canonical monitor-first workspace', async ({ page }) => {
    const app = page.locator('[data-testid="sovereign-monitor-app"]');
    await expect(app).toHaveAttribute('data-layout', 'monitor-first-live-workspace');
    await expect(app).toHaveAttribute('aria-label', 'Sovereign Workspace Monitor');

    const builder = page.locator('[data-layout="live-desktop-monitor-primary"]');
    await expect(builder).toBeVisible();
    await expect(page.locator('[data-testid="sovereign-live-monitor-primary"]')).toBeVisible();
    await expect(page.locator('[data-testid="live-workspace-monitor-desktop"]')).toBeVisible();
    await expect(page.locator('[data-testid="monitor-communication-dock"]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Menü', exact: true })).toBeVisible();
  });

  test('2. The restored menu exposes the protected GitHub credential handoff', async ({ page }) => {
    await page.getByRole('button', { name: 'Menü', exact: true }).click();

    const menu = page.getByRole('dialog', { name: 'Sovereign Seitenmenü' });
    await expect(menu).toBeVisible();
    const githubAccess = menu.getByRole('button', { name: /GitHub Access/ });
    await expect(githubAccess).toBeVisible();
    await githubAccess.click();

    const accessCard = page.getByRole('group', { name: 'GitHub-Zugang' });
    await expect(accessCard).toBeVisible();
    await expect(page.locator('[data-testid="github-access-modal"]')).toHaveCount(0);
    await accessCard.getByRole('button', { name: 'Zugang eingeben' }).click();

    const accessDialog = page.getByRole('dialog', { name: 'GitHub-Zugang' });
    await expect(accessDialog).toBeVisible();
    await expect(accessDialog.getByLabel(/GitHub Token/)).toHaveAttribute('type', 'password');
    await expect(accessDialog.getByRole('button', { name: 'Abbrechen' })).toBeFocused();
  });

  test('3. The compact communication dock keeps the route catalog collapsed', async ({ page }) => {
    const composer = page.getByLabel('Codeauftrag an Sovereign');
    await expect(composer).toBeVisible();
    await expect(composer).toHaveAttribute(
      'placeholder',
      'Codeauftrag eingeben · Enter sendet · Shift+Enter neue Zeile',
    );

    await composer.fill('');
    await expect(page.getByRole('button', { name: 'Senden', exact: true })).toBeDisabled();
    await composer.fill('Prüfe den Build und bereite nur einen Draft PR vor.');
    await expect(page.getByRole('button', { name: 'Senden', exact: true })).toBeEnabled();

    const routeTrigger = page.locator('[data-testid="sovereign-llm-route-picker-trigger"]');
    await expect(routeTrigger).toBeVisible();
    await expect(routeTrigger).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByRole('dialog', { name: 'LLM-Modell auswählen' })).toHaveCount(0);

    await routeTrigger.click();
    await expect(page.getByRole('dialog', { name: 'LLM-Modell auswählen' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: 'LLM-Modell auswählen' })).toHaveCount(0);
  });

  test('4. Monitor controls remain the single primary surface', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Live Monitor' })).toBeVisible();
    await expect(page.locator('[data-testid="monitor-action-controls"]')).toBeVisible();
    await expect(page.locator('[data-testid="monitor-runtime-action-trace"]')).toBeAttached();
    await expect(page.locator('[data-testid="monitor-communication-dock"]')).toBeVisible();
    await expect(page.locator('[data-testid="sovereign-chat-body-window"]')).toHaveCount(0);
  });

  test('5. Monitor shell and restored menu remain reachable at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.locator('[data-testid="sovereign-monitor-app"]')).toBeVisible();
    await expect(page.locator('[data-testid="sovereign-live-monitor-primary"]')).toBeVisible();
    await expect(page.locator('[data-testid="monitor-communication-dock"]')).toBeVisible();

    await page.getByRole('button', { name: 'Menü', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Sovereign Seitenmenü' })).toBeVisible();
  });

  test('6. The evidence observatory route remains independently reachable', async ({ page }) => {
    await page.goto('/observatory');
    await expect(page.locator('[data-testid="evidence-observatory-atlas"]')).toBeVisible(EXTENDED_TIMEOUT);
    await expect(page.locator('[data-testid="sovereign-monitor-app"]')).toHaveCount(0);
  });
});
