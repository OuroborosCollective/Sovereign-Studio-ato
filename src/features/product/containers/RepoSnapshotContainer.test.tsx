import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
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

afterEach(() => {
  delete window.__sovereignSetupState;
  delete (window as typeof window & { __sovereignRuntimeCoachState?: unknown }).__sovereignRuntimeCoachState;
});

describe('RepoSnapshotContainer', () => {
  it('renders status, memory hints and file list', () => {
    render(<RepoSnapshotContainer {...baseProps()} />);

    expect(screen.getByTestId('repo-snapshot-container')).toBeDefined();
    expect(screen.getByText(/Snapshot: 1 entries/i)).toBeDefined();
    expect(screen.getByText(/Remote Aha Memory/i)).toBeDefined();
  });

  it('renders the runtime coach monitor without DOM installers', () => {
    (window as typeof window & { __sovereignRuntimeCoachState?: unknown }).__sovereignRuntimeCoachState = {
      lamp: 'green',
      title: 'Bereit für Auftrag',
      message: 'Repository ist geladen. Auftrag eingeben und Package erstellen.',
      action: 'Package bauen',
      thinking: false,
      source: 'runtime-library',
      updatedAt: 1_700_000_000_000,
    };

    render(<RepoSnapshotContainer {...baseProps()} />);

    expect(screen.getByTestId('react-coach-monitor')).toBeDefined();
    expect(screen.getByText('Agenten-Monitor · Sovereign Bot')).toBeDefined();
    expect(screen.getByText('Bereit für Auftrag')).toBeDefined();
    expect(screen.getByText(/Aktion: Package bauen/i)).toBeDefined();
  });

  it('updates coach monitor from runtime coach events', async () => {
    render(<RepoSnapshotContainer {...baseProps()} />);

    window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', {
      detail: {
        lamp: 'red',
        title: 'Runtime Stopper',
        message: 'Runtime wartet auf einen sicheren nächsten Schritt.',
        action: 'Telemetry und Health prüfen',
        thinking: false,
        source: 'telemetry',
        updatedAt: 1_700_000_001_000,
      },
    }));

    await waitFor(() => {
      expect(screen.getByText('Runtime Stopper')).toBeDefined();
      expect(screen.getByText(/Telemetry und Health prüfen/i)).toBeDefined();
    });
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

  it('publishes current repo setup state to the coach bridge', async () => {
    const listener = vi.fn();
    window.addEventListener('sovereign:setup-state', listener);

    render(<RepoSnapshotContainer {...baseProps()} accessValue="token-for-test-only" />);

    await waitFor(() => {
      expect(window.__sovereignSetupState).toMatchObject({
        hasToken: true,
        tokenStatus: 'valid',
        repoReady: true,
        setupPhase: 'repo-loaded',
        isBusy: false,
      });
    });
    expect(listener).toHaveBeenCalled();

    window.removeEventListener('sovereign:setup-state', listener);
  });
});
