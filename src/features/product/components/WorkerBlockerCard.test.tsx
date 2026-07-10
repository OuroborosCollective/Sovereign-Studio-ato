/**
 * WorkerBlockerCard tests
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { WorkerBlockerCard, WorkerDegradedBanner } from './WorkerBlockerCard';
import type { DevChatWorkerDiagnostic } from '../runtime/devChatWorkerBridge';
import { SOVEREIGN_WORKER_CHAT } from '../runtime/devChatWorkerBridge';

const mockDiagnostic: DevChatWorkerDiagnostic = {
  route: SOVEREIGN_WORKER_CHAT,
  model: 'gemini-2.0-flash',
  messageCount: 1,
  scope: 'network',
  canClientFix: true,
  nextAction: 'retry',
};

const mockBlocker = {
  message: 'Worker unavailable',
  diagnostic: mockDiagnostic,
  createdAt: Date.now(),
};

const diagnosticText = [
  'Worker nicht erreichbar',
  'Scope: network · HTTP 500',
  'Health: secret=ok · upstream=ok',
  'Antwortauszug: Failed to fetch',
].join('\n');

describe('WorkerBlockerCard', () => {
  it('renders blocker message', () => {
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onRetry={() => {}}
        onExplain={() => {}}
      />
    );
    expect(screen.getByText('Worker nicht erreichbar')).toBeTruthy();
  });

  it('calls onRetry when retry button clicked', () => {
    const onRetry = vi.fn();
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onRetry={onRetry}
        onExplain={() => {}}
      />
    );
    fireEvent.click(screen.getByText('Retry'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('calls onExplain when explain button clicked', () => {
    const onExplain = vi.fn();
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onRetry={() => {}}
        onExplain={onExplain}
      />
    );
    fireEvent.click(screen.getByText('Diagnose erklären'));
    expect(onExplain).toHaveBeenCalledTimes(1);
  });

  it('calls onRetryWithMessage when retry with message clicked', () => {
    const onRetryWithMessage = vi.fn();
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onRetry={() => {}}
        onRetryWithMessage={onRetryWithMessage}
        onExplain={() => {}}
        userMessage="retry this"
      />
    );
    fireEvent.click(screen.getByText('Retry'));
    expect(onRetryWithMessage).toHaveBeenCalledWith('retry this');
  });

  it('falls back to onRetry and hides Sovereign Agent handoff when the supplied message is a diagnostic', () => {
    const onRetry = vi.fn();
    const onRetryWithMessage = vi.fn();
    const onAgentInstead = vi.fn();
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onRetry={onRetry}
        onRetryWithMessage={onRetryWithMessage}
        onExplain={() => {}}
        onAgentInstead={onAgentInstead}
        userMessage={diagnosticText}
      />
    );
    expect(screen.queryByText(/Sovereign Agent für Code-Auftrag/i)).toBeNull();
    fireEvent.click(screen.getByText('Retry'));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onRetryWithMessage).not.toHaveBeenCalled();
    expect(onAgentInstead).not.toHaveBeenCalled();
  });

  it('shows Sovereign Agent action when user has code intent', () => {
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onRetry={() => {}}
        onExplain={() => {}}
        onAgentInstead={(msg) => {}}
        userMessage="fix this bug in the code"
      />
    );
    expect(screen.getByText(/Sovereign Agent für Code-Auftrag/i)).toBeTruthy();
  });

  it('hides Sovereign Agent action when user has no code intent', () => {
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onRetry={() => {}}
        onExplain={() => {}}
        onAgentInstead={(msg) => {}}
        userMessage="hello world"
      />
    );
    expect(screen.queryByText(/Sovereign Agent für Code-Auftrag/i)).toBeNull();
  });
});

describe('WorkerDegradedBanner', () => {
  it('renders offline message', () => {
    render(<WorkerDegradedBanner blocker={mockBlocker} />);
    expect(screen.getByText('Worker offline')).toBeTruthy();
  });

  it('calls onRetry when clicked (legacy)', () => {
    const onRetry = vi.fn();
    render(<WorkerDegradedBanner blocker={mockBlocker} onRetry={onRetry} />);
    fireEvent.click(screen.getByTestId('worker-degraded-banner'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('calls onRetryWithMessage when provided', () => {
    const onRetryWithMessage = vi.fn();
    render(
      <WorkerDegradedBanner
        blocker={mockBlocker}
        onRetryWithMessage={onRetryWithMessage}
        userMessage="retry this request"
      />
    );
    fireEvent.click(screen.getByTestId('worker-degraded-banner'));
    expect(onRetryWithMessage).toHaveBeenCalledWith('retry this request');
  });

  it('falls back to onRetry when the supplied message is a diagnostic', () => {
    const onRetry = vi.fn();
    const onRetryWithMessage = vi.fn();
    render(
      <WorkerDegradedBanner
        blocker={mockBlocker}
        onRetry={onRetry}
        onRetryWithMessage={onRetryWithMessage}
        userMessage={diagnosticText}
      />
    );
    fireEvent.click(screen.getByTestId('worker-degraded-banner'));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onRetryWithMessage).not.toHaveBeenCalled();
  });

  it('falls back to onRetry when onRetryWithMessage not provided', () => {
    const onRetry = vi.fn();
    render(
      <WorkerDegradedBanner
        blocker={mockBlocker}
        onRetry={onRetry}
        userMessage="retry this request"
      />
    );
    fireEvent.click(screen.getByTestId('worker-degraded-banner'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
