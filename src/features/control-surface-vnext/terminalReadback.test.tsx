import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { onlineManager } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import SovereignControlSurfaceVNext from './App';
import type { SovereignBackendAdapter } from './adapter/interface';
import type { SovereignJob } from './types/domain';

const session = vi.hoisted(() => ({
  user: { id: 'owner-terminal', isGuest: false },
  ensureGuestSession: vi.fn(async () => undefined),
}));
vi.mock('../user/useUserStore', () => ({ useUserStore: () => session }));

afterEach(() => onlineManager.setOnline(true));

it('updates the existing terminal chat message when later readback supplies the final cause', async () => {
  let cause = 'Tool execution error: Custom test command is not allowlisted';
  const getJob = vi.fn(async (): Promise<SovereignJob> => ({
    id: 'agent-terminal', runId: 'agent-terminal', phase: 'BLOCKED',
    createdAt: '2026-10-08T13:46:17Z', updatedAt: '2026-10-08T13:46:45Z',
    logs: [], workspaceState: { modifiedFiles: ['Tester'], currentRevision: '' },
    error: { message: cause },
  }));
  const adapter: SovereignBackendAdapter = {
    getJob, runSingleAgent: vi.fn(), resumeJob: vi.fn(), abortJob: vi.fn(),
    prepareDraftPr: vi.fn(), createDraftPr: vi.fn(),
    getToolchains: vi.fn(async () => []), getSkills: vi.fn(async () => []),
    getIntegrations: vi.fn(async () => []),
    restoreLatestRepositoryRun: vi.fn(async () => ({ jobId: 'agent-terminal', status: 'blocked' })),
  };
  const view = render(<SovereignControlSurfaceVNext adapter={adapter} />);
  const old = await screen.findByText(/RUN BLOCKED.*agent-terminal/s);
  expect(old).toHaveTextContent(cause);
  cause = 'AGENTS_TURN_LIMIT_EXHAUSTED';
  await act(async () => {
    onlineManager.setOnline(false);
    onlineManager.setOnline(true);
  });
  const updated = await screen.findByText(/RUN BLOCKED.*AGENTS_TURN_LIMIT_EXHAUSTED/s);
  expect(updated).not.toHaveTextContent('Custom test command');
  expect(screen.getAllByText(/RUN BLOCKED.*agent-terminal/s)).toHaveLength(1);
  view.unmount();
});
