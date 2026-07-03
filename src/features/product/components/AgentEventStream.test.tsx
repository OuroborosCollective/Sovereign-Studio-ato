import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AgentEventStream } from './AgentEventStream';
import {
  createIdleSnapshot,
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

describe('AgentEventStream', () => {
  it('shows intent_detected as Auftrag erkannt, not as active OpenHands work', () => {
    render(<AgentEventStream snapshot={intentSnapshot()} />);

    expect(screen.getByText('Auftrag erkannt')).toBeTruthy();
    expect(screen.queryByText(/OpenHands arbeitet/i)).toBeNull();
  });

  it('shows executor_starting as starting, not as running work', () => {
    render(<AgentEventStream snapshot={transitionExecutorStarting(intentSnapshot(), 'openhands')} />);

    expect(screen.getByText('OpenHands startet…')).toBeTruthy();
    expect(screen.queryByText(/OpenHands arbeitet/i)).toBeNull();
  });

  it('shows OpenHands arbeitet only when runtime state or job status is running', () => {
    render(<AgentEventStream snapshot={runningSnapshot()} job={runningJob()} />);

    expect(screen.getByText('OpenHands arbeitet…')).toBeTruthy();
  });

  it('shows blocked, failed and draft-pr-ready terminal truth without fabricating progress', () => {
    const blocked = transitionBlocked(intentSnapshot(), 'GitHub-Schreibzugang fehlt.');
    const { rerender, container } = render(<AgentEventStream snapshot={blocked} />);

    expect(screen.getByText('Executor blockiert')).toBeTruthy();

    const draftReady = transitionDraftPrReady(
      runningSnapshot(),
      'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/488',
    );
    rerender(<AgentEventStream snapshot={draftReady} />);

    expect(screen.getByText('Draft PR bereit')).toBeTruthy();
    expect(screen.getByText(/Draft PR öffnen/i)).toBeTruthy();
    expect(container.textContent).not.toContain('%');
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

    expect(screen.getByText('Auftrag erkannt')).toBeTruthy();
    expect(screen.queryByText(/unknown\/repo/i)).toBeNull();
  });

  it('renders nothing for an idle snapshot without events', () => {
    const { container } = render(<AgentEventStream snapshot={createIdleSnapshot('idle-trace')} />);

    expect(container.textContent).toBe('');
  });
});
