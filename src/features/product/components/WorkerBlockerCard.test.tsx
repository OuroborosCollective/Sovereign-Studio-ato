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

  it('disables retry when no previous request or retry callback exists', () => {
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onExplain={() => {}}
      />
    );
    const button = screen.getByRole('button', { name: /Retry unavailable/i });
    expect(button).toBeDisabled();
    expect(screen.getByText('Retry nicht verfügbar')).toBeTruthy();
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

  it('shows Sovereign Agent action only with structured permission', () => {
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onRetry={() => {}}
        onExplain={() => {}}
        onAgentInstead={() => {}}
        userMessage="fix this bug in the code"
        allowAgentAction
      />
    );
    expect(screen.getByText(/Sovereign Agent für Code-Auftrag/i)).toBeTruthy();
  });

  it('does not infer Agent permission from code words in the user message', () => {
    render(
      <WorkerBlockerCard
        blocker={mockBlocker}
        onRetry={() => {}}
        onExplain={() => {}}
        onAgentInstead={() => {}}
        userMessage="fix this bug in the code"
      />
    );
    expect(screen.queryByText(/Sovereign Agent für Code-Auftrag/i)).toBeNull();
  });
});

describe('WorkerDegradedBanner', () => {
  it('does not duplicate the actionable blocker card', () => {
    const { container } = render(<WorkerDegradedBanner blocker={mockBlocker} />);
    expect(container.firstChild).toBeNull();
  });
});
