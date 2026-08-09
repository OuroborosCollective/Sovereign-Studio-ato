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
});
