import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { syncApproval } from './approvalSyncClient';

const originalEnv = import.meta.env.VITE_APPROVAL_SYNC_URL;

describe('syncApproval', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    import.meta.env.VITE_APPROVAL_SYNC_URL = originalEnv;
  });

  it('fails when sync url is missing', async () => {
    import.meta.env.VITE_APPROVAL_SYNC_URL = '';

    await expect(syncApproval({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      workflowCode: 'export const x = 1;',
      manifestJson: '{}',
      blueprint: 'test',
    })).rejects.toThrow(/VITE_APPROVAL_SYNC_URL fehlt/);
  });

  it('returns branch and pull request url on success', async () => {
    import.meta.env.VITE_APPROVAL_SYNC_URL = 'https://example.com/approval-sync';

    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ok: true,
      branchName: 'sovereign-approval/20260609-test',
      pullRequestUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/999',
    }), { status: 200 })));

    await expect(syncApproval({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      workflowCode: 'export const x = 1;',
      manifestJson: '{}',
      blueprint: 'test',
    })).resolves.toEqual({
      ok: true,
      branchName: 'sovereign-approval/20260609-test',
      pullRequestUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/999',
    });
  });

  it('throws when server returns ok false', async () => {
    import.meta.env.VITE_APPROVAL_SYNC_URL = 'https://example.com/approval-sync';

    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ok: false,
      code: 'GITHUB_SYNC_TOKEN_MISSING',
      message: 'Server secret missing.',
    }), { status: 500 })));

    await expect(syncApproval({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      workflowCode: 'export const x = 1;',
      manifestJson: '{}',
      blueprint: 'test',
    })).rejects.toThrow(/Server secret missing/);
  });

  it('throws when success response has no target link', async () => {
    import.meta.env.VITE_APPROVAL_SYNC_URL = 'https://example.com/approval-sync';

    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ok: true,
      branchName: 'branch-only',
      pullRequestUrl: '',
    }), { status: 200 })));

    await expect(syncApproval({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      workflowCode: 'export const x = 1;',
      manifestJson: '{}',
      blueprint: 'test',
    })).rejects.toThrow(/Ziel-Link fehlt/);
  });
});