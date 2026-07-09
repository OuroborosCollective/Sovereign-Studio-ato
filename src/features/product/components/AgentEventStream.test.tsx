import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AgentEventStream } from './AgentEventStream';
import {
  createIdleSnapshot,
  transitionAccessReady,
  transitionAccessRequired,
  transitionAccessValidating,
  transitionBlocked,
  transitionDraftPrReady,
  transitionExecutorRunning,
  transitionExecutorStarting,
  transitionIntentDetected,
  type AgentWorkSnapshot,
} from '../runtime/agentWorkRuntime';
import type { OpenHandsJobSnapshot } from '../runtime/openhandsEnterpriseRuntime';

function intentSnapshot(repo = 'OuroborosCollective/Sovereign-Studio-ato'): AgentWorkSnapshot {
  return transitionIntentDetected(createIdleSnapshot('trace-aes'), repo, 'main');
}

function runningSnapshot(): AgentWorkSnapshot {
  return transitionExecutorRunning(
    transitionExecutorStarting(intentSnapshot(), 'openhands'),
    'job-1',
  );
}

function runningJob(overrides: Partial<OpenHandsJobSnapshot> = {}): OpenHandsJobSnapshot {
  return {
    status: 'running',
    changedFiles: [],
    events: [],
    ...overrides,
  };
}

function visibleTextWithoutStyle(container: HTMLElement): string {
  const clone = container.cloneNode(true) as HTMLElement;
  for (const style of clone.querySelectorAll('style')) {
    style.remove();
  }
  return clone.textContent ?? '';
}

describe('AgentEventStream', () => {
  it('shows intent_detected as Auftrag erkannt, not as active OpenHands work', () => {
    render(<AgentEventStream snapshot={intentSnapshot()} />);

    expect(screen.getAllByText(/Auftrag erkannt/).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/Sovereign Agent arbeitet/i)).toBeNull();
  });

  it('shows executor_starting as starting, not as running work', () => {
    render(<AgentEventStream snapshot={transitionExecutorStarting(intentSnapshot(), 'openhands')} />);

    expect(screen.getByText('Sovereign Agent startet…')).toBeTruthy();
    expect(screen.queryByText(/Sovereign Agent arbeitet/i)).toBeNull();
  });

  it('lets verified backend running status override a local starting snapshot', () => {
    render(
      <AgentEventStream
        snapshot={transitionExecutorStarting(intentSnapshot(), 'openhands')}
        job={runningJob()}
      />,
    );

    expect(screen.getByText('Sovereign Agent arbeitet…')).toBeTruthy();
    expect(screen.queryByText('Sovereign Agent startet…')).toBeNull();
  });

  it('shows Sovereign Agent arbeitet only when runtime state or job status is running', () => {
    render(<AgentEventStream snapshot={runningSnapshot()} job={runningJob()} />);

    expect(screen.getByText('Sovereign Agent arbeitet…')).toBeTruthy();
  });

  it('keeps access states visible as access truth, not generic intent truth', () => {
    const accessRequired = transitionAccessRequired(intentSnapshot());
    const accessValidating = transitionAccessValidating(accessRequired);
    const accessReady = transitionAccessReady(accessValidating);
    const { rerender } = render(<AgentEventStream snapshot={accessRequired} />);

    expect(screen.getAllByText('GitHub-Zugang erforderlich').length).toBeGreaterThanOrEqual(1);

    rerender(<AgentEventStream snapshot={accessValidating} />);
    expect(screen.getByText('GitHub-Zugang wird geprüft…')).toBeTruthy();

    rerender(<AgentEventStream snapshot={accessReady} />);
    expect(screen.getByText('GitHub-Zugang bereit')).toBeTruthy();
  });

  it('shows blocked, failed and draft-pr-ready terminal truth without fabricating progress', () => {
    const blocked = transitionBlocked(intentSnapshot(), 'GitHub-Schreibzugang fehlt.');
    const { rerender, container } = render(<AgentEventStream snapshot={blocked} />);

    expect(screen.getAllByText(/Executor blockiert/).length).toBeGreaterThanOrEqual(1);

    const draftReady = transitionDraftPrReady(
      runningSnapshot(),
      'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/488',
    );
    rerender(
      <AgentEventStream
        snapshot={draftReady}
        job={runningJob()}
        onCancel={() => undefined}
      />,
    );

    expect(screen.getAllByText(/Draft PR bereit/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Draft PR öffnen/i)).toBeTruthy();
    expect(screen.queryByText('Abbrechen')).toBeNull();
    expect(visibleTextWithoutStyle(container)).not.toContain('%');
  });

  it('renders changed files only from supplied OpenHands job snapshot', () => {
    render(
      <AgentEventStream
        snapshot={runningSnapshot()}
        job={runningJob({ changedFiles: ['src/features/product/components/AgentEventStream.tsx'] })}
      />,
    );

    expect(screen.getByText('Dateien: 1')).toBeTruthy();
    expect(screen.getByText('AgentEventStream.tsx')).toBeTruthy();
  });

  it('does not display unknown/repo as real repository truth', () => {
    render(<AgentEventStream snapshot={intentSnapshot('unknown/repo')} />);

    expect(screen.getAllByText(/Auftrag erkannt/).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/unknown\/repo/i)).toBeNull();
  });

  it('renders nothing for an idle snapshot without events', () => {
    const { container } = render(<AgentEventStream snapshot={createIdleSnapshot('idle-trace')} />);

    expect(container.textContent).toBe('');
  });
});
