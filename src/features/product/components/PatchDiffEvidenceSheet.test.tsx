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
});
