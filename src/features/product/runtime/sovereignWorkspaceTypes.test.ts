import { describe, it, expect } from 'vitest';
import { createMaskedWorkspaceEvent } from './sovereignWorkspaceTypes';

describe('sovereignWorkspaceTypes secret masking', () => {
  it('masks GitHub Personal Access Tokens inside workspace events', () => {
    // ghp_ followed by exactly 36 alphanumeric characters
    const secret = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz';
    const event = createMaskedWorkspaceEvent(
      'workspace_requested',
      'job-123',
      `Cloned repository with token ${secret}`,
      { token: secret, safeField: 'allgood' }
    );

    expect(event.detail).toBe('Cloned repository with token [GITHUB_TOKEN_MASKED]');
    expect(event.data?.token).toBe('[SECRET_MASKED]');
    expect(event.data?.safeField).toBe('allgood');
  });

  it('masks API keys in details and recursively in data objects', () => {
    // sk- followed by exactly 48 alphanumeric characters
    const secret = 'sk-123456789012345678901234567890123456789012345678';
    const event = createMaskedWorkspaceEvent(
      'workspace_requested',
      'job-123',
      `Setting up API environment key ${secret}`,
      {
        provider: {
          key: secret,
          name: 'OpenAI',
        },
        simple_token: 'token: my_secret_token_123',
      }
    );

    expect(event.detail).toBe('Setting up API environment key [API_KEY_MASKED]');
    expect((event.data?.provider as any)?.key).toBe('[SECRET_MASKED]');
    expect((event.data?.provider as any)?.name).toBe('OpenAI');
    expect(event.data?.simple_token).toBe('[SECRET_MASKED]');
  });

  it('masks Bearer tokens in details', () => {
    const event = createMaskedWorkspaceEvent(
      'workspace_requested',
      'job-123',
      'Failed call with Bearer abcd_efgh_ijkl_mnop'
    );

    expect(event.detail).toBe('Failed call with Bearer [TOKEN_MASKED]');
  });
});
