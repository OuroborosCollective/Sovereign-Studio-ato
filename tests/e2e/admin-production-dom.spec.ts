import { expect, test } from '@playwright/test';

const expectedRevision = process.env.SOVEREIGN_EXPECTED_REVISION?.trim() ?? '';
const adminKey = process.env.SOVEREIGN_ADMIN_E2E_KEY?.trim() ?? '';

if (!/^[0-9a-f]{40}$/.test(expectedRevision)) {
  throw new Error('SOVEREIGN_EXPECTED_REVISION must be one exact 40-character commit SHA.');
}
if (!adminKey) {
  throw new Error('SOVEREIGN_ADMIN_E2E_KEY is required for the real admin DOM gate.');
}

test('production /admin is the revision-bound React Free-Revolver surface', async ({ page, request }) => {
  const healthResponse = await request.get('/health', {
    headers: { Accept: 'application/json' },
  });
  expect(healthResponse.status()).toBe(200);
  const health = await healthResponse.json() as {
    sourceRevision?: string;
    imageDigest?: string;
  };
  expect(health.sourceRevision).toBe(expectedRevision);
  expect(health.imageDigest).not.toBe('unverified');

  const adminResponse = await page.goto('/admin', { waitUntil: 'domcontentloaded' });
  expect(adminResponse?.status()).toBe(200);
  expect(adminResponse?.headers()['x-sovereign-admin-surface']).toBe('react');
  expect(adminResponse?.headers()['x-sovereign-source-revision']).toBe(expectedRevision);

  await expect(page.locator('html')).toHaveAttribute('data-sovereign-surface', 'react-admin');
  await expect(page.getByTestId('sovereign-react-admin')).toBeVisible();
  await expect(page.getByText('Sovereign Enterprise Admin', { exact: true })).toHaveCount(0);

  await page.getByLabel('Bestehender Admin-Key').fill(adminKey);
  await page.getByRole('button', { name: 'Verbinden & speichern' }).click();
  await expect(page.getByRole('navigation', { name: 'Admin-Bereiche' })).toBeVisible({
    timeout: 30_000,
  });

  await page.getByRole('button', { name: 'LLM' }).click();
  await expect(page.getByRole('navigation', { name: 'LLM-Laufzeitbereiche' })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole('button', { name: 'Free Revolver' }).click();
  await expect(page.getByTestId('free-revolver-control-center')).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId('freellm-provider-registration')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Kostenfreie Provider sicher verbinden' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sicher prüfen und Free-Routen anlegen' })).toBeVisible();

  await page.getByTestId('freellm-managed-provider-select').click();
  await expect(page.getByLabel('Provider-Name')).toHaveValue('FreeLLM API 0.5.0 · interner Docker');
  await expect(page.getByLabel('API-Basis')).toHaveValue('http://freellmapi:3001/v1');
  await expect(page.getByLabel('Authentifizierung')).toHaveValue('managed-bearer');
});
