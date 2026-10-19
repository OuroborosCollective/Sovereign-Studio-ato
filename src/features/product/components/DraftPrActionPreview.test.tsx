import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DraftPrActionPreview } from './DraftPrActionPreview';

describe('DraftPrActionPreview', () => {
  it('shows the exact action scope and only invokes the explicit confirm callback', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <DraftPrActionPreview
        repoUrl="https://github.com/OuroborosCollective/Sovereign-Studio-ato"
        branch="sovereign/chatgpt/example"
        expectedHeadSha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        mission="Create the reviewed Draft PR"
        changedFileCount={3}
        evidenceSource="agent"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByTestId('draft-pr-action-preview')).toHaveAttribute('role', 'alertdialog');
    expect(screen.getByTestId('draft-pr-preview-head')).toHaveTextContent('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
    expect(screen.getByText(/serverseitige Agent-Changed-File-Evidence/)).toBeDefined();

    fireEvent.click(screen.getByTestId('cancel-draft-pr-action-preview'));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('confirm-draft-pr-action-preview'));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('provides accessible titles and focus styles on action buttons without redundant aria-label overrides, and supports Escape key dismiss', () => {
    const onCancel = vi.fn();
    render(
      <DraftPrActionPreview
        repoUrl="https://github.com/OuroborosCollective/Sovereign-Studio-ato"
        branch="sovereign/chatgpt/example"
        expectedHeadSha="1234567890abcdef1234567890abcdef12345678"
        mission="Test mission"
        changedFileCount={2}
        evidenceSource="staged"
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );

    const cancelButton = screen.getByTestId('cancel-draft-pr-action-preview');
    expect(cancelButton).not.toHaveAttribute('aria-label');
    expect(cancelButton).toHaveAttribute('title', 'Übergabe an Runtime abbrechen');
    expect(cancelButton).toHaveClass('hover:opacity-90');

    const confirmButton = screen.getByTestId('confirm-draft-pr-action-preview');
    expect(confirmButton).not.toHaveAttribute('aria-label');
    expect(confirmButton).toHaveAttribute('title', 'Draft PR nach Serverprüfung posten');
    expect(confirmButton).toHaveClass('hover:opacity-90');

    expect(screen.getByText(/OuroborosCollective\/Sovereign-Studio-ato#sovereign\/chatgpt\/example/)).toHaveAttribute(
      'title',
      'https://github.com/OuroborosCollective/Sovereign-Studio-ato#sovereign/chatgpt/example',
    );

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
