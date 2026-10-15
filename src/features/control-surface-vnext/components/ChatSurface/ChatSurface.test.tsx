import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatSurface } from './ChatSurface';

describe('live command surface integration', () => {
  it('keeps mission controls collapsed while preserving the response and composer', () => {
    render(<ChatSurface messages={[{ id: 'blocked-response', role: 'assistant', sender: 'SOVEREIGN_AGENT', content: 'Test command blocked; choose an allowed test.', timestamp: '2026-10-08T07:44:15Z' }]} jobPhase="BLOCKED" />);
    const controls = screen.getByTestId('vnext-mission-controls');
    expect(controls).not.toHaveAttribute('open');
    expect(screen.getByRole('log')).toHaveTextContent('Test command blocked; choose an allowed test.');
    expect(controls).not.toContainElement(screen.getByRole('log'));
    expect(controls).not.toContainElement(screen.getByRole('textbox', { name: 'Mission to Sovereign' }));
    fireEvent.click(screen.getByText(/Mission controls/));
    expect(controls).toHaveAttribute('open');
    expect(screen.getByLabelText('ROUTE')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Mission controls/));
    expect(controls).not.toHaveAttribute('open');
    expect(screen.getByRole('log')).toHaveTextContent('Test command blocked');
  });

  it('keeps the paid reservation disclosure visible outside collapsed controls', () => {
    render(<ChatSurface messages={[]} executionMode="paid" />);
    const disclosure = screen.getByText(/Dispatch authorizes a credit reservation/);
    expect(screen.getByTestId('vnext-mission-controls')).not.toContainElement(disclosure);
    expect(disclosure).toBeVisible();
    expect(screen.getByText(/Selected route unavailable/)).toBeVisible();
    expect(screen.getByTestId('builder__start-task')).toBeDisabled();
  });

  it('renders code copy controls and rejects script links in incoming messages', () => {
    render(<ChatSurface messages={[{ id: 'response', role: 'assistant', sender: 'SOVEREIGN_AGENT', content: '```ts\nconst value = 1;\n```\n[unsafe](javascript:alert)', timestamp: '2026-10-02T00:00:00Z' }]} onSubmitOrder={vi.fn()} />);
    expect(screen.getByText('const value = 1;')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy|kopieren/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'unsafe' })).toHaveAttribute('href', 'about:blank');
  });

  it('keeps abort pending distinct from completion and prevents repeat submission', () => {
    const abort = vi.fn();
    const { rerender } = render(<ChatSurface messages={[]} onSubmitOrder={vi.fn()} jobPhase="EXECUTING" onAbortJob={abort} />);
    fireEvent.click(screen.getByRole('button', { name: 'ABORT' }));
    expect(abort).toHaveBeenCalledTimes(1);
    rerender(<ChatSurface messages={[]} onSubmitOrder={vi.fn()} jobPhase="EXECUTING" onAbortJob={abort} isAborting />);
    const pending = screen.getByRole('button', { name: 'REQUESTING…' });
    expect(pending).toBeDisabled();
    expect(pending).toHaveAttribute('aria-busy', 'true');
    fireEvent.click(pending);
    expect(abort).toHaveBeenCalledTimes(1);
    expect(screen.getByText('EXECUTING')).toBeInTheDocument();
  });
});
