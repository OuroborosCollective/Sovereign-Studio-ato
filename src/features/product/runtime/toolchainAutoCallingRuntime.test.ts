import { describe, expect, it, vi } from 'vitest';
import {
  buildToolchainAutoContext,
  detectToolchainWriteIntent,
  extractToolchainFileTarget,
  planToolchainAutoCalls,
} from './toolchainAutoCallingRuntime';
import type { DevChatRepoSnapshot } from './devChatWorkerBridge';

const repoSnapshot: DevChatRepoSnapshot = {
  owner: 'OuroborosCollective',
  repo: 'Sovereign-Studio-ato',
  branch: 'main',
  name: 'Sovereign-Studio-ato',
  repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
  fileCount: 3,
  dirs: ['src', 'scripts'],
  files: [
    { type: 'blob', path: 'src/features/product/containers/BuilderContainer.tsx', size: 1000 },
    { type: 'blob', path: 'src/features/product/runtime/devChatWorkerBridge.ts', size: 800 },
    { type: 'blob', path: 'scripts/sovereign-backend/app.py', size: 1200 },
  ],
};

describe('toolchainAutoCallingRuntime', () => {
  it('plans read-only toolchain calls from chat intent and repo file mention', () => {
    const calls = planToolchainAutoCalls({
      submittedText: 'Bitte typecheck und Tests planen und BuilderContainer.tsx lesen.',
      repoSnapshot,
    });

    expect(calls.map((call) => call.tool)).toEqual([
      'plan_sandbox_commands',
      'github_read_file',
    ]);
    expect(calls.every((call) => call.writeAction === false)).toBe(true);
    expect(calls[1].args).toMatchObject({
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
      path: 'src/features/product/containers/BuilderContainer.tsx',
      ref: 'main',
    });
  });

  it('detects write intent without creating write tool calls', () => {
    const calls = planToolchainAutoCalls({
      submittedText: 'Bitte fixe app.py und erstelle einen Draft PR.',
      repoSnapshot,
    });

    expect(detectToolchainWriteIntent('Bitte fixe app.py und erstelle einen Draft PR.')).toBe(true);
    expect(calls.map((call) => call.tool)).toEqual(['github_read_file']);
    expect(calls.every((call) => call.writeAction === false)).toBe(true);
  });

  it('extracts exact and basename file mentions from the loaded repo snapshot', () => {
    expect(extractToolchainFileTarget('lies scripts/sovereign-backend/app.py', repoSnapshot))
      .toBe('scripts/sovereign-backend/app.py');
    expect(extractToolchainFileTarget('lies devChatWorkerBridge.ts', repoSnapshot))
      .toBe('src/features/product/runtime/devChatWorkerBridge.ts');
  });

  it('builds a compact context from backend proxy tool results', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body ?? '{}')) as { tool: string };
      return new Response(JSON.stringify({ ok: true, tool: body.tool, result: { command: 'tsc --noEmit' } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const result = await buildToolchainAutoContext({
      submittedText: 'Bitte Toolchain erklären und verify planen.',
      repoSnapshot,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.context).toContain('Sovereign Toolchain Auto-Calls');
    expect(result.context).toContain('toolchain_briefing');
    expect(result.context).toContain('plan_sandbox_commands');
  });
});
