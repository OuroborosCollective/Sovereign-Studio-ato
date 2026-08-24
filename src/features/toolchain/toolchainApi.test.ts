import { afterEach, describe, expect, it, vi } from 'vitest';
import { toolchainApi } from './toolchainApi';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('toolchainApi endpoint contracts', () => {
  it('binds read-only POST operations to their exact backend routes and payloads', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/toolchain/universal/invoke')) {
        return new Response(JSON.stringify({
          ok: true,
          result: {
            ok: true,
            runtime: 'embedded',
            version: 'v1',
            evidenceHash: 'a'.repeat(64),
            failureFamilies: [],
            nextLogicalFailures: [],
            policy: {},
          },
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/toolchain/github/list-branches')) {
        return new Response(JSON.stringify({ branches: [{ name: 'main' }] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/api/toolchain/github/search-code')) {
        return new Response(JSON.stringify({ items: [], total: 0 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/api/toolchain/audit-log')) {
        return new Response(JSON.stringify({ entries: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/api/toolchain/sandbox-plan')) {
        return new Response(JSON.stringify({
          goal: 'verify contracts',
          commands: ['pnpm run test:frontend-endpoints'],
          note: 'read-only plan',
          rules: { push_to_main: false, draft_pr: true, confirm: true },
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({ error: 'unexpected endpoint' }), { status: 500 });
    });
    vi.stubGlobal('fetch', fetchMock);

    await toolchainApi.diagnoseRuntime({
      mission: 'Inspect one runtime failure',
      evidence_text: 'bounded evidence',
    });
    await toolchainApi.listBranches({ owner: 'acme', repo: 'runtime' });
    await toolchainApi.searchCode({ owner: 'acme', repo: 'runtime', q: 'EngineBoundary' });
    await toolchainApi.sandboxPlan({ goal: 'verify contracts' });
    await toolchainApi.getAuditLog();

    const calls = fetchMock.mock.calls.map(([input, init]) => ({
      url: String(input),
      init: init as RequestInit,
    }));
    expect(calls.map(call => call.url)).toEqual([
      'https://sovereign-backend.arelorian.de/api/toolchain/universal/invoke',
      'https://sovereign-backend.arelorian.de/api/toolchain/github/list-branches',
      'https://sovereign-backend.arelorian.de/api/toolchain/github/search-code',
      'https://sovereign-backend.arelorian.de/api/toolchain/sandbox-plan',
      'https://sovereign-backend.arelorian.de/api/toolchain/audit-log',
    ]);
    expect(calls.map(call => call.init.method ?? 'GET')).toEqual([
      'POST',
      'POST',
      'POST',
      'POST',
      'GET',
    ]);
    expect(calls.every(call => call.init.credentials === 'include')).toBe(true);
    expect(calls.every(call => (
      (call.init.headers as Record<string, string>)['Content-Type'] === 'application/json'
    ))).toBe(true);
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      tool: 'runtime_failure_diagnose',
      args: { mission: 'Inspect one runtime failure', evidence_text: 'bounded evidence' },
    });
    expect(JSON.parse(String(calls[1].init.body))).toEqual({ owner: 'acme', repo: 'runtime' });
    expect(JSON.parse(String(calls[2].init.body))).toEqual({
      owner: 'acme',
      repo: 'runtime',
      q: 'EngineBoundary',
    });
    expect(JSON.parse(String(calls[3].init.body))).toEqual({ goal: 'verify contracts' });
  });

  it('rejects a failed backend response instead of returning a synthetic result', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: 'sandbox_plan_blocked',
    }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    })));

    await expect(toolchainApi.sandboxPlan({ goal: 'unsafe effect' }))
      .rejects.toThrow('sandbox_plan_blocked');
  });
});
