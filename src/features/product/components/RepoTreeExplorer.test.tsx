import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { RepoTreeExplorer } from './RepoTreeExplorer';

describe('RepoTreeExplorer', () => {
  const snapshot = {
    owner: 'owner', repo: 'repo', branch: 'main', name: 'repo', repoUrl: 'local', fileCount: 2,
    files: [{ path: 'src/App.tsx', type: 'blob' as const }, { path: 'README.md', type: 'blob' as const }], dirs: ['src'],
  };

  it('renders empty state', () => {
    render(<RepoTreeExplorer snapshot={null} onClose={() => {}} onFileClick={() => {}} />);
    expect(screen.getByText(/Repo-Snapshot fehlt/i)).toBeTruthy();
  });

  it('calls file callback', () => {
    const onFileClick = vi.fn();
    render(<RepoTreeExplorer snapshot={snapshot} onClose={() => {}} onFileClick={onFileClick} />);
    fireEvent.click(screen.getByText('App.tsx'));
    expect(onFileClick).toHaveBeenCalledWith('src/App.tsx');
  });

  it('calls close callback', () => {
    const onClose = vi.fn();
    render(<RepoTreeExplorer snapshot={snapshot} onClose={onClose} onFileClick={() => {}} />);
    fireEvent.click(screen.getByText('Schließen'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
