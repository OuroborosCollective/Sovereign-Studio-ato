import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { buildGeneratedFileDiffReport } from '../runtime/generatedFileDiffPreview';
import { PatchDiffEvidenceSheet } from './PatchDiffEvidenceSheet';

const report = buildGeneratedFileDiffReport(
  [{ path: 'README.md', content: '# Updated\n', reason: 'Update documentation' }],
  [{ path: 'README.md', content: '# Original\n', found: true }],
);

describe('PatchDiffEvidenceSheet', () => {
  it('requires an explicit user confirmation callback', () => {
    const onConfirm = vi.fn();
    render(
      <PatchDiffEvidenceSheet
        report={report}
        confirmed={false}
        onConfirm={onConfirm}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('confirm-patch-diff'));

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(screen.getByText('README.md')).toBeDefined();
    expect(screen.getByText(/Original/)).toBeDefined();
    expect(screen.getByText(/Updated/)).toBeDefined();
  });

  it('does not allow a second confirmation once runtime state is confirmed', () => {
    const onConfirm = vi.fn();
    render(
      <PatchDiffEvidenceSheet
        report={report}
        confirmed
        onConfirm={onConfirm}
        onClose={vi.fn()}
      />,
    );

    const button = screen.getByTestId('confirm-patch-diff');
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('closes on Escape key press, links dialog landmark, and renders diff list with focusable pre block', () => {
    const onClose = vi.fn();
    render(
      <PatchDiffEvidenceSheet
        report={report}
        confirmed={false}
        onConfirm={vi.fn()}
        onClose={onClose}
      />,
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-labelledby', 'patch-diff-title');

    const title = screen.getByText('Patch Diff');
    expect(title).toHaveAttribute('id', 'patch-diff-title');

    const list = screen.getByRole('list', { name: 'Patch-Dateien Diff-Liste' });
    expect(list).toBeInTheDocument();

    const preBlock = screen.getByLabelText('Diff-Vorschau für README.md');
    expect(preBlock).toHaveAttribute('tabIndex', '0');
    expect(preBlock).toHaveClass('focus-visible:ring-2');

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
