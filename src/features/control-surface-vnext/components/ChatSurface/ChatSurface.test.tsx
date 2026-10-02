import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatSurface } from './ChatSurface';

describe('live command surface integration', () => {
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
