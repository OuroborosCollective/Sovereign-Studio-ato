import { describe, expect, it, vi } from 'vitest';
import {
  canPerformGitHubWrite,
  maskGitHubToken,
  requestGitHubAccess,
  validateGitHubTokenForRepo,
  validateGitHubTokenFormat,
} from './githubAccessRuntime';

// Deliberately nonfunctional, generated input-rule fixtures; no live credentials.
const modernToken = 'ghs_' + '12345_' + [
  'header-opaque'.repeat(5),
  'payload_opaque'.repeat(36),
  'signature-opaque'.repeat(6),
].join('.');

const target = {
  repository: 'https://github.com/example/test-project',
  branch: 'main',
  expectedBaseSha: 'a'.repeat(40),
};

describe('GitHub installation token input compatibility', () => {
  it('accepts variable-length opaque installation credentials without JWT decoding', () => {
    expect(modernToken.length).toBeGreaterThan(520);
    expect(validateGitHubTokenFormat(modernToken).isValid).toBe(true);
    expect(validateGitHubTokenFormat(` ${modernToken} `).isValid).toBe(true);
  });

  it.each(['ghp_', 'gho_', 'ghu_', 'ghs_', 'ghr_', 'github_pat_'])('preserves %s legacy input compatibility', prefix => {
    expect(validateGitHubTokenFormat(prefix + 'a'.repeat(36)).isValid).toBe(true);
  });

  it.each(['\r\nInjected: value', '\0', '/', '"', 'é'])('rejects unsafe suffix %j', suffix => {
    expect(validateGitHubTokenFormat(modernToken + suffix).isValid).toBe(false);
  });

  it('bounds opaque installation-token input', () => {
    expect(validateGitHubTokenFormat('ghs_' + 'a.'.repeat(2500)).isValid).toBe(false);
  });

  it('never grants write authority merely because a format is accepted', () => {
    const pending = requestGitHubAccess(maskGitHubToken(modernToken));
    expect(pending.state).toBe('requested');
    expect(canPerformGitHubWrite(pending)).toBe(false);
    expect(JSON.stringify(pending)).not.toContain(modernToken);
  });

  it('passes the unchanged opaque input only to the scoped backend boundary', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, scope: 'unit-scope-only' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: false, canWrite: false }), { status: 200 }));
    const result = await validateGitHubTokenForRepo(modernToken, target, fetcher, 'https://backend.example');
    expect(fetcher).toHaveBeenCalledTimes(2);
    for (const [url, init] of fetcher.mock.calls) {
      expect(String(url)).toMatch(/^https:\/\/backend\.example\/api\/user\/agent\/github-access\/(scope|validate)$/);
      expect(JSON.parse(String(init?.body)).githubAccessToken).toBe(modernToken);
      expect(init?.credentials).toBe('include');
    }
    expect(result.ok).toBe(false);
    expect(result.canWrite).toBe(false);
  });

  it('keeps API failures closed even for an accepted installation-token format', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 403 }));
    const result = await validateGitHubTokenForRepo(modernToken, target, fetcher, 'https://backend.example');
    expect(result.ok).toBe(false);
    expect(result.canWrite).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
