import { expect, test } from '@playwright/test';

const productionUrl = (process.env.SOVEREIGN_ADMIN_PRODUCTION_URL
  ?? 'https://sovereign-backend.arelorian.de').replace(/\/+$/, '');
const expectedRevision = (process.env.SOVEREIGN_EXPECTED_REVISION ?? '').trim();

test('production /admin is the exact revision-bound React Free Revolver bundle', async ({ page, request }) => {
  expect(expectedRevision).toMatch(/^[0-9a-f]{40}$/);

  const healthResponse = await request.get(`${productionUrl}/health/live`, {
    failOnStatusCode: true,
  });
  const health = await healthResponse.json() as {
    sourceRevision?: string;
    adminProducer?: string;
    adminArtifactReady?: boolean;
  };
  expect(health.sourceRevision).toBe(expectedRevision);
  expect(health.adminProducer).toBe('react-admin-dist');
  expect(health.adminArtifactReady).toBe(true);

  const navigation = await page.goto(`${productionUrl}/admin`, {
    waitUntil: 'domcontentloaded',
  });
  expect(navigation?.status()).toBe(200);
  expect(page.url()).toBe(`${productionUrl}/admin/`);
  expect(navigation?.headers()['x-sovereign-admin-producer']).toBe('react-admin-dist');
  expect(navigation?.headers()['x-sovereign-source-revision']).toBe(expectedRevision);

  const adminRoot = page.getByTestId('sovereign-react-admin-root');
  await expect(adminRoot).toBeVisible();
  await expect(adminRoot).toHaveAttribute('data-admin-producer', 'react-admin-dist');
  await expect(adminRoot).toHaveAttribute('data-source-revision', expectedRevision);
  await expect(page.getByRole('heading', { name: 'Admin-Verbindung' })).toBeVisible();
  await expect(page.getByText('Sovereign Enterprise Admin', { exact: true })).toHaveCount(0);

  const scriptSources = await page.locator('script[src]').evaluateAll(elements =>
    elements.map(element => (element as HTMLScriptElement).src).filter(Boolean),
  );
  expect(scriptSources.length).toBeGreaterThan(0);

  let deployedJavaScript = '';
  for (const source of scriptSources) {
    const scriptResponse = await request.get(source, { failOnStatusCode: true });
    deployedJavaScript += await scriptResponse.text();
  }

  expect(deployedJavaScript).toContain('FreeLLM API 0.5.0 auswählen');
  expect(deployedJavaScript).toContain('Kostenfreie Provider sicher verbinden');
  expect(deployedJavaScript).toContain('http://freellmapi:3001/v1');
  expect(deployedJavaScript).not.toContain('ENTERPRISE_ADMIN_HTML');
});
