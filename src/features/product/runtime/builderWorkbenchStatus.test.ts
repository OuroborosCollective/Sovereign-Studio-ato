import { describe, expect, it } from 'vitest';
import {
  deriveDraftPrStatus,
  deriveEditedFileEntries,
  deriveErrorEntries,
  deriveLogEntries,
  deriveSystemActionEntries,
  deriveWorkbenchStatusSlots,
  type WorkbenchStatusInput,
} from './builderWorkbenchStatus';

function baseInput(overrides: Partial<WorkbenchStatusInput> = {}): WorkbenchStatusInput {
  return {
    logs: [],
    workerBlocker: null,
    chatRepoError: null,
    ...overrides,
  };
}

describe('builderWorkbenchStatus', () => {
  it('shows explicit empty states when there is no runtime data, never fake content', () => {
    const slots = deriveWorkbenchStatusSlots(baseInput());
    expect(slots.find((slot) => slot.id === 'files')?.label).toBe('Changed');
    for (const slot of slots) {
      if (slot.id === 'draftPr') {
        expect(slot.value).toBe('fehlt');
      } else {
        expect(slot.value).toBe('0');
      }
      expect(slot.items).toHaveLength(0);
      expect(slot.emptyLabel.length).toBeGreaterThan(0);
    }
  });

  it('counts system actions but excludes tab navigation noise and raw signal logs', () => {
    const input = baseInput({
      logs: [
        { ts: '10:00:00', level: 'info', msg: 'Tab → chat (manual)', tabId: 'chat' },
        { ts: '10:00:01', level: 'signal', msg: 'Signal[router] → active', tabId: 'router' },
        { ts: '10:00:02', level: 'info', msg: 'Worker retry requested by user', tabId: 'router' },
      ],
    });
    const actions = deriveSystemActionEntries(input);
    expect(actions).toHaveLength(1);
    expect(actions[0]).toContain('Worker retry requested by user');
  });

  it('derives edited files only from real Sovereign Agent changed files', () => {
    const input = baseInput({
      agentJob: {
        status: 'running',
        changedFiles: ['src/App.tsx', 'src/features/product/containers/BuilderContainer.tsx'],
        events: [],
      },
    });
    expect(deriveEditedFileEntries(input)).toEqual([
      'src/App.tsx',
      'src/features/product/containers/BuilderContainer.tsx',
    ]);
  });

  it('lists every log entry chronologically for the Logs slot', () => {
    const input = baseInput({
      logs: [
        { ts: '10:00:00', level: 'info', msg: 'a', tabId: 'router' },
        { ts: '10:00:01', level: 'warn', msg: 'b', tabId: 'router' },
      ],
    });
    expect(deriveLogEntries(input)).toHaveLength(2);
  });

  it('collects worker blocker, repo error and failed/blocked Sovereign Agent jobs as errors', () => {
    const input = baseInput({
      workerBlocker: {
        message: 'Worker HTTP 500',
        diagnostic: { scope: 'worker' } as never,
        createdAt: Date.now(),
      },
      chatRepoError: 'Repo tree fetch failed',
      agentJob: { status: 'failed', changedFiles: [], events: [], lastError: 'boom' },
    });
    const errors = deriveErrorEntries(input);
    expect(errors.some((e) => e.includes('Worker HTTP 500'))).toBe(true);
    expect(errors.some((e) => e.includes('Repo tree fetch failed'))).toBe(true);
    expect(errors.some((e) => e.includes('boom'))).toBe(true);
  });

  it('reports all warning logs as errors, as keyword-based filtering of resolved blockers is forbidden by the Manifest', () => {
    const errors = deriveErrorEntries(baseInput({
      githubState: 'ready',
      logs: [
        { ts: '10:00:00', level: 'warn', msg: 'Write intent blocked: GitHub write access missing', tabId: 'router' },
        { ts: '10:00:01', level: 'warn', msg: 'Other active blocker', tabId: 'router' },
      ],
    }));

    expect(errors).toEqual([
      '10:00:00 · Write intent blocked: GitHub write access missing',
      '10:00:01 · Other active blocker'
    ]);
  });

  it('reports Draft PR as bereit only when a real PR url exists', () => {
    expect(deriveDraftPrStatus(baseInput()).label).toBe('fehlt');
    expect(
      deriveDraftPrStatus(baseInput({ agentJob: { status: 'running', changedFiles: [], events: [] } })).label,
    ).toBe('läuft');
    expect(
      deriveDraftPrStatus(
        baseInput({ agentJob: { status: 'running', changedFiles: [], events: [], draftPrUrl: 'https://x' } }),
      ).label,
    ).toBe('bereit');
    expect(deriveDraftPrStatus(baseInput({ publishedPrUrl: 'https://x' })).label).toBe('bereit');
  });

  it('marks the errors slot with error tone only when errors exist', () => {
    const clean = deriveWorkbenchStatusSlots(baseInput()).find((s) => s.id === 'errors')!;
    expect(clean.tone).toBe('neutral');
    const dirty = deriveWorkbenchStatusSlots(
      baseInput({ chatRepoError: 'boom' }),
    ).find((s) => s.id === 'errors')!;
    expect(dirty.tone).toBe('error');
  });
});
