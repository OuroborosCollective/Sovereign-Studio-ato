import { describe, expect, it } from 'vitest';
import {
  buildGitHubHeaders,
  createGitHubAuthSession,
  hasGitHubToken,
  normalizeGitHubToken,
  redactGitHubToken,
  requireGitHubToken,
  stripTokenFromText,
} from './githubAuthSession';

describe('githubAuthSession', () => {
  it('normalizes and detects session-only tokens', () => {
    expect(normalizeGitHubToken('  ghp_abc  ')).toBe('ghp_abc');
    expect(hasGitHubToken('  ghp_abc  ')).toBe(true);
    expect(hasGitHubToken('')).toBe(false);
  });

  it('redacts tokens for logs and telemetry', () => {
    expect(redactGitHubToken('ghp_1234567890')).toBe('ghp_…7890');
    expect(redactGitHubToken('short')).toBe('<redacted-token>');
    expect(redactGitHubToken('')).toBe('<no-token>');
  });

  it('builds GitHub headers with optional JSON and auth', () => {
    const headers = buildGitHubHeaders({ token: ' ghp_token ', json: true }) as Record<string, string>;
    expect(headers.Accept).toBe('application/vnd.github+json');
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers.Authorization).toBe('Bearer ghp_token');
  });

  it('requires tokens only for explicit write paths', () => {
    expect(requireGitHubToken(' ghp_token ', 'Draft PR')).toBe('ghp_token');
    expect(() => requireGitHubToken('', 'Draft PR')).toThrow('Draft PR requires a GitHub token');
  });

  it('strips raw tokens and other secrets from text', () => {
    const text = stripTokenFromText(
      'failed with ghp_1234567890 and sk-abc1234567890abcdefghijkl',
      'ghp_1234567890'
    );
    expect(text).toContain('ghp_…7890');
    expect(text).not.toContain('ghp_1234567890');
    expect(text).toContain('sk-****');
    expect(text).not.toContain('sk-abc1234567890');
    expect(createGitHubAuthSession(' token ').redactedToken).toBe('<redacted-token>');
  });
});
