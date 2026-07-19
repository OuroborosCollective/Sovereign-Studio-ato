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
import type { SovereignActionEvent } from './sovereignActionStreamRuntime';

function baseInput(overrides: Partial<WorkbenchStatusInput> = {}): WorkbenchStatusInput {
  return {
    logs: [],
    actionEvents: [],
    workerBlocker: null,
    chatRepoError: null,
    ...overrides,
  };
}

function actionEvent(overrides: Partial<SovereignActionEvent> = {}): SovereignActionEvent {
  return {
    id: 'event-1',
    createdAt: 1,
    kind: 'input_received',
    route: 'runtime',
    label: 'Eingabe empfangen',
    state: 'done',
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

  it('counts only explicitly operational Action-Stream events', () => {
    const actions = deriveSystemActionEntries(baseInput({
      logs: [
        { ts: '10:00:00', level: 'info', msg: 'Worker retry requested by user', tabId: 'router' },
        { ts: '10:00:01', level: 'signal', msg: 'Signal[router] → active', tabId: 'router' },
      ],
      actionEvents: [
        actionEvent({ id: 'input', kind: 'input_received', label: 'Eingabe empfangen' }),
        actionEvent({ id: 'route', kind: 'route_selected', label: 'Route gewählt', state: 'running' }),
        actionEvent({
          id: 'request',
          kind: 'llm_request_started',
          route: 'worker',
          label: 'LLM Request gestartet',
          state: 'running',
        }),
        actionEvent({
          id: 'response',
          kind: 'llm_response_received',
          route: 'worker',
          label: 'LLM Response empfangen',
          state: 'done',
        }),
        actionEvent({
          id: 'patch',
          kind: 'patch_generated',
          route: 'github-patch',
          label: 'Patch generiert',
          detail: 'src/App.tsx',
          state: 'done',
        }),
        actionEvent({
          id: 'failed',
          kind: 'agent_tool_finished',
          route: 'agent-job',
          label: 'Tool fehlgeschlagen',
          state: 'failed',
        }),
      ],
    }));

    expect(actions).toEqual([
      'LLM Request gestartet',
      'Patch generiert · src/App.tsx',
    ]);
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

  it('keeps warning and error text in Logs and counts only structured failed events', () => {
    const input = baseInput({
      logs: [
        { ts: '10:00:00', level: 'warn', msg: 'GitHub access missing', tabId: 'router' },
        { ts: '10:00:01', level: 'error', msg: 'Worker request failed', tabId: 'router' },
      ],
      actionEvents: [
        actionEvent({
          id: 'failed-patch',
          kind: 'failed',
          route: 'direct-github-patch',
          label: 'Direct Patch fehlgeschlagen',
          detail: 'Patch rejected',
          state: 'failed',
        }),
        actionEvent({
          id: 'blocked',
          kind: 'patch_blocked',
          route: 'github-patch',
          label: 'Patch wartet',
          state: 'blocked',
        }),
      ],
    });

    expect(deriveLogEntries(input)).toEqual([
      '10:00:00 · [warn] GitHub access missing',
      '10:00:01 · [error] Worker request failed',
    ]);
    expect(deriveErrorEntries(input)).toEqual([
      'Direct Patch fehlgeschlagen · Patch rejected',
    ]);
  });

  it('does not duplicate a structured worker failure when a canonical blocker exists', () => {
    const errors = deriveErrorEntries(baseInput({
      workerBlocker: {
        message: 'Worker HTTP 500',
        diagnostic: { scope: 'worker' } as never,
        createdAt: Date.now(),
      },
      actionEvents: [
        actionEvent({
          id: 'worker-failed',
          kind: 'failed',
          route: 'worker',
          label: 'Worker blockiert',
          detail: 'Worker HTTP 500',
          state: 'failed',
        }),
      ],
    }));

    expect(errors).toEqual(['Worker blockiert · Worker HTTP 500']);
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
