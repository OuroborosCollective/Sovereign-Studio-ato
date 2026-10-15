import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OwnerInteractionModal } from './OwnerInteractionModal';

vi.mock('../Modal', () => ({
  Modal: ({ children }: { children: React.ReactNode }) => <div role="dialog">{children}</div>,
}));

describe('OwnerInteractionModal', () => {
  it('renders an approval as an action preview without inventing parameters', () => {
    render(
      <OwnerInteractionModal
        interaction={{
          id: 'approval-42',
          kind: 'draft_pr_readiness',
          prompt: 'The server requests approval to create exactly one GitHub Draft PR.',
          requiresText: false,
          options: ['approve', 'reject'],
          context: 'create_draft_pr',
        }}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText('ACTION PREVIEW / AWAITING OWNER DECISION')).toBeInTheDocument();
    expect(screen.getByText('draft_pr_readiness')).toBeInTheDocument();
    expect(screen.getByText('approval-42')).toBeInTheDocument();
    expect(screen.getByText('The server requests approval to create exactly one GitHub Draft PR.')).toBeInTheDocument();
    expect(screen.queryByText('amount')).not.toBeInTheDocument();
    expect(screen.queryByText('recipient')).not.toBeInTheDocument();
  });

  it('submits the explicit server-supported reject and approve decisions', () => {
    const onSubmit = vi.fn();
    render(
      <OwnerInteractionModal
        interaction={{
          id: 'approval-77',
          kind: 'external_write',
          prompt: 'Create one Draft PR on the selected repository.',
          requiresText: false,
          options: ['approve', 'reject'],
        }}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /REJECT/i }));
    expect(onSubmit).toHaveBeenCalledWith({ interactionId: 'approval-77', response: 'reject' });

    fireEvent.click(screen.getByRole('button', { name: /^APPROVE$/i }));
    expect(onSubmit).toHaveBeenCalledWith({ interactionId: 'approval-77', response: 'approve' });
  });

  it('keeps protected approvals fail-closed to approve/reject input', () => {
    const onSubmit = vi.fn();
    render(
      <OwnerInteractionModal
        interaction={{
          id: 'approval-91',
          kind: 'protected_owner_input',
          prompt: 'Protected owner approval is required.',
          requiresText: true,
        }}
        onSubmit={onSubmit}
      />,
    );

    const textarea = screen.getByPlaceholderText('approve or reject');
    fireEvent.change(textarea, { target: { value: 'something else' } });
    fireEvent.click(screen.getByRole('button', { name: /SEND DIRECTIVE/i }));
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(textarea, { target: { value: 'approve' } });
    fireEvent.click(screen.getByRole('button', { name: /SEND DIRECTIVE/i }));
    expect(onSubmit).toHaveBeenCalledWith({ interactionId: 'approval-91', response: 'approve' });
  });

  it('sends generic owner directives verbatim', () => {
    const onSubmit = vi.fn();
    render(
      <OwnerInteractionModal
        interaction={{
          id: 'run-123',
          kind: 'owner-directive',
          prompt: 'The persisted run needs a human-provided instruction.',
          requiresText: true,
        }}
        onSubmit={onSubmit}
      />,
    );

    const textarea = screen.getByPlaceholderText('Enter the exact owner response.');
    fireEvent.change(textarea, { target: { value: 'Keep the current branch; do not publish.' } });
    fireEvent.click(screen.getByRole('button', { name: /SEND DIRECTIVE/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      interactionId: 'run-123',
      response: 'Keep the current branch; do not publish.',
    });
  });
});
