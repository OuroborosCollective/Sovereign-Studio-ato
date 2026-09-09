import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright';

const appUrl = process.env.SOVEREIGN_E2E_APP_URL?.trim() || 'http://127.0.0.1:3000';
if (!['http://127.0.0.1:3000', 'https://127.0.0.1:3000'].includes(appUrl)) {
  throw new Error('Browser boot check only supports its own loopback preview.');
}
const tlsSpki = process.env.SOVEREIGN_E2E_TLS_SPKI || '';
const secrets = Object.entries(process.env)
  .filter(([key, value]) => /TOKEN|SECRET|PASSWORD|ACCOUNT_KEY/i.test(key) && value && value.length >= 8)
  .map(([, value]) => value);
function redact(value) {
  let text = String(value);
  for (const secret of secrets) text = text.split(secret).join('[redacted]');
  return text.replace(/\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+)\b/g, '[redacted]')
    .replace(/(Bearer\s+)\S+/gi, '$1[redacted]').slice(0, 2500);
}
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', '3000', '--strictPort'], { stdio: 'ignore' });
const serverExit = once(server, 'exit').catch(() => undefined);
let browser;
try {
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (server.exitCode !== null) throw new Error(`Preview exited: ${server.exitCode}`);
    try {
      const response = await fetch(`${appUrl}/`, { signal: AbortSignal.timeout(2000) });
      ready = response.ok;
    } catch { /* Bounded startup observation, not a success signal. */ }
    if (ready) break;
    await delay(500);
  }
  if (!ready) throw new Error('Preview did not become reachable');
  browser = await chromium.launch({
    args: appUrl.startsWith('https:') && /^[A-Za-z0-9+/]{43}=$/.test(tlsSpki)
      ? [`--ignore-certificate-errors-spki-list=${tlsSpki}`] : [],
  });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  page.on('pageerror', error => errors.push(redact(error.stack || error.message)));
  page.on('requestfailed', request => {
    const url = new URL(request.url());
    if (url.origin === appUrl) console.log('BOOT_REQUEST_FAILED', redact(url.pathname), redact(request.failure()?.errorText));
  });
  await page.goto(`${appUrl}/`, { waitUntil: 'domcontentloaded' });
  try {
    await page.getByTestId('sovereign-release-chat').waitFor({ state: 'visible', timeout: 20000 });
    if (errors.length) throw new Error('Browser reported uncaught errors during boot');
    console.log('RELEASE_BROWSER_BOOT=PASS (mount only; not Draft-PR evidence)');
  } catch (error) {
    console.error('RELEASE_BROWSER_BOOT=FAIL');
    for (const entry of errors) console.error('BOOT_PAGE_ERROR', entry);
    // This fresh context has received no GitHub credential or user mission.
    console.error('BOOT_VISIBLE_TEXT', redact(await page.locator('body').innerText()));
    throw error;
  }
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null) {
    server.kill('SIGTERM');
    await Promise.race([serverExit, delay(5000)]);
    if (server.exitCode === null) server.kill('SIGKILL');
    await serverExit;
  }
}
