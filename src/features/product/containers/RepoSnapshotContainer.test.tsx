import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RepoSnapshotContainer } from './RepoSnapshotContainer';

function baseProps() {
  return {
    repoUrl: 'https://example.test/org/repo',
    repoBranch: 'main',
    accessValue: '',
    repoStatus: 'Ready',
    isRepoBusy: false,
    runtimeBusy: false,
    repoFiles: [{ path: 'README.md', type: 'blob' as const, size: 10 }],
    memoryHints: 'Remote Aha Memory',
    onRepoUrlChange: vi.fn(),
    onRepoBranchChange: vi.fn(),
    onAccessValueChange: vi.fn(),
    onLoadRepo: vi.fn(),
    onSaveView: vi.fn(),
    onRestoreView: vi.fn(),
    onClearView: vi.fn(),
  };
}

describe('RepoSnapshotContainer', () => {
  it('renders status, memory hints and file list', () => {
    render(<RepoSnapshotContainer {...baseProps()} />);

    expect(screen.getByTestId('repo-snapshot-container')).toBeDefined();
    expect(screen.getByText(/Snapshot: 1 entries/i)).toBeDefined();
    expect(screen.getByText(/Remote Aha Memory/i)).toBeDefined();
  });

  it('emits input changes and button actions', () => {
    const props = baseProps();
    render(<RepoSnapshotContainer {...props} />);

    fireEvent.change(screen.getByLabelText(/Repository URL/i), { target: { value: 'https://example.test/next/repo' } });
    fireEvent.change(screen.getByLabelText(/Repository branch/i), { target: { value: 'develop' } });
    fireEvent.click(screen.getByRole('button', { name: /Load Repo/i }));
    fireEvent.click(screen.getByRole('button', { name: /Save Session/i }));
    fireEvent.click(screen.getByRole('button', { name: /Restore Session/i }));
    fireEvent.click(screen.getByRole('button', { name: /Clear View/i }));

    expect(props.onRepoUrlChange).toHaveBeenCalledWith('https://example.test/next/repo');
    expect(props.onRepoBranchChange).toHaveBeenCalledWith('develop');
    expect(props.onLoadRepo).toHaveBeenCalledOnce();
    expect(props.onSaveView).toHaveBeenCalledOnce();
    expect(props.onRestoreView).toHaveBeenCalledOnce();
    expect(props.onClearView).toHaveBeenCalledOnce();
  });

  it('blocks load without repository url and save without ready files', () => {
    render(<RepoSnapshotContainer {...baseProps()} repoUrl="" repoFiles={[]} />);

    expect(screen.getByRole('button', { name: /Load Repo/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Save Session/i })).toBeDisabled();
  });

  it('blocks all actions while busy', () => {
    render(<RepoSnapshotContainer {...baseProps()} runtimeBusy={true} />);

    expect(screen.getByRole('button', { name: /Load Repo/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Save Session/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Restore Session/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Clear View/i })).toBeDisabled();
  });
});
