import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { requireLoginAccountId, requireSameOrigin, requireVerifiedSessionIdentity } from '../../../tests/e2e/helpers/live-session-contract';

const accountId = '00000000-0000-4000-8000-000000000123';
const user = { id: accountId, isGuest: false, isBanned: false, creditStateVerified: true };

describe('live vNext authentication and agent session boundary', () => {
  it('uses one preview origin for both real auth modules and the agent adapter', () => {
    const workflow = readFileSync('.github/workflows/e2e-testing.yml', 'utf8');
    const liveJob = workflow.split(/^  live-five-path-draft-pr:\s*$/m)[1];
    expect(liveJob).toBeDefined();
    const envBlock = liveJob.split('    env:\n')[1].split('    steps:')[0];
    const value = (key: string) => envBlock.match(new RegExp(`^      ${key}: (.+)$`, 'm'))?.[1].trim();
    const appUrl = value('SOVEREIGN_E2E_APP_URL');
    expect(appUrl).toBe('https://127.0.0.1:3000');
    expect(value('VITE_ADMIN_API_BASE')).toBe(appUrl);
    expect(value('VITE_SOVEREIGN_AGENT_API_URL')).toBe(appUrl);
    expect(value('SOVEREIGN_E2E_BACKEND_PROXY_TARGET')).toMatch(/^https:\/\//);
  });

  it('preserves Secure cookies using real loopback TLS and narrowly pinned test trust', () => {
    const workflow = readFileSync('.github/workflows/e2e-testing.yml', 'utf8');
    const vite = readFileSync('vite.config.ts', 'utf8');
    const browser = readFileSync('playwright.config.ts', 'utf8');
    const prepare = readFileSync('scripts/prepare-live-e2e-tls.sh', 'utf8');
    expect(workflow).toContain('bash scripts/prepare-live-e2e-tls.sh');
    expect(vite).toContain('LIVE_PREVIEW_TLS_CONFIGURATION_REQUIRED');
    expect(vite).toContain('cert: readFileSync(tlsCert), key: readFileSync(tlsKey)');
    expect(vite).toContain('secure: true');
    expect(browser).toContain('LIVE_PREVIEW_HTTPS_AND_EXACT_CERTIFICATE_PIN_REQUIRED');
    expect(browser).toContain('--ignore-certificate-errors-spki-list=${localTlsSpki}');
    expect(browser).not.toContain('ignoreHTTPSErrors: true');
    expect(browser).not.toContain("'--ignore-certificate-errors'");
    expect(prepare).toContain('NODE_EXTRA_CA_CERTS=$CERT');
    expect(prepare).toContain('umask 077');
    expect(prepare).toContain('-verify_ip 127.0.0.1');
  });

  it('rejects a login-only success without a matching browser-session readback', () => {
    expect(requireLoginAccountId(200, { id: accountId })).toBe(accountId);
    expect(() => requireVerifiedSessionIdentity(401, user, accountId)).toThrow('LIVE_SESSION_HTTP_401');
  });

  it('accepts the exact non-guest server-confirmed identity', () => {
    expect(requireVerifiedSessionIdentity(200, user, accountId)).toBe(accountId);
  });

  it.each([null, [], {}, { id: '' }])('rejects incomplete login identity %#', (payload) => {
    expect(() => requireLoginAccountId(200, payload)).toThrow();
  });

  it.each([401, 403, 429, 500])('rejects authentication HTTP %i even with a user-shaped body', (status) => {
    expect(() => requireLoginAccountId(status, { id: accountId })).toThrow(`LIVE_AUTH_HTTP_${status}`);
  });

  it.each([
    { ...user, id: 'another-account' },
    { ...user, isGuest: true },
    { ...user, isGuest: undefined },
    { ...user, isBanned: true },
    { ...user, creditStateVerified: false },
    null,
    [],
  ])('rejects cross-account, guest, banned or unverified readback %#', (payload) => {
    expect(() => requireVerifiedSessionIdentity(200, payload, accountId)).toThrow();
  });

  it('rejects an absent expected identity rather than accepting the current account', () => {
    expect(() => requireVerifiedSessionIdentity(200, user, '')).toThrow('LIVE_SESSION_ACCOUNT_MISMATCH');
  });

  it('accepts same-origin requests but refuses the former split-origin route', () => {
    expect(() => requireSameOrigin('http://127.0.0.1:3000/api/auth/me', 'http://127.0.0.1:3000/')).not.toThrow();
    expect(() => requireSameOrigin('https://backend.invalid/api/auth/me', 'http://127.0.0.1:3000/')).toThrow('LIVE_AUTH_AGENT_ORIGIN_MISMATCH');
    expect(() => requireSameOrigin('http://127.0.0.1:3001/api/auth/me', 'http://127.0.0.1:3000/')).toThrow();
  });

  it('keeps the actual browser and backend readback in the live execution path', () => {
    const live = readFileSync('tests/e2e/five-draft-pr-paths.spec.ts', 'utf8');
    expect(live).toContain('page.waitForResponse');
    expect(live).toContain("page.request.get(new URL('/api/auth/me', page.url()).href");
    expect(live).toContain('requireVerifiedSessionIdentity(session.status()');
    expect(live).toContain('requireSameOrigin(login.url(), page.url())');
    expect(live).toContain('authenticationReadbacks,');
    expect(live).not.toContain('await registration.text()');
    expect(live).not.toContain('await issued.text()');
    expect(live).not.toContain("getByText('AUTHENTICATED', { exact: true }).count()");
  });
});
