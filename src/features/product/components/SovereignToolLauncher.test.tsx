import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SovereignToolLauncher } from './SovereignToolLauncher';
import { useLauncherStore } from '../../launcher/useLauncherStore';
import { createEmptySovereignToolShortcutContext } from '../runtime/sovereignToolShortcutRuntime';
import { useSovereignToolInspectionStore } from '../runtime/sovereignToolInspectionRuntime';

beforeEach(() => {
  useLauncherStore.setState({ isMenuOpen: false, windows: [] });
  useSovereignToolInspectionStore.getState().resetEvidence();
});

describe('SovereignToolLauncher', () => {
  it('shows explicit gate state for all ten shortcuts', () => {
    render(<SovereignToolLauncher onSelect={vi.fn()} />);
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));

    const items = screen.getAllByRole('menuitem');
    expect(items).toHaveLength(10);
    for (const item of items) {
      expect(item.getAttribute('data-gate-state')).toBeTruthy();
      expect(item.getAttribute('data-can-open')).toMatch(/true|false/);
      expect(item.getAttribute('title')).toContain('\n');
    }
  });

  it('blocks Files until repo file evidence exists', () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <SovereignToolLauncher onSelect={onSelect} runtimeContext={createEmptySovereignToolShortcutContext()} />,
    );

    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    const blockedFiles = screen.getByRole('menuitem', { name: 'Files' });
    expect(blockedFiles).toBeDisabled();
    expect(blockedFiles).toHaveAttribute('data-gate-state', 'setup_required');
    fireEvent.click(blockedFiles);
    expect(onSelect).not.toHaveBeenCalled();

    rerender(
      <SovereignToolLauncher
        onSelect={onSelect}
        runtimeContext={{ ...createEmptySovereignToolShortcutContext(), repoReady: true, repoFileCount: 7 }}
      />,
    );
    fireEvent.click(screen.getByRole('menuitem', { name: 'Files' }));
    expect(onSelect).toHaveBeenCalledWith('files');
  });

  it('routes an explicitly clicked blocked shortcut to its blocker handler without opening a tool', () => {
    const onSelect = vi.fn();
    const onBlockedSelect = vi.fn();
    render(
      <SovereignToolLauncher
        onSelect={onSelect}
        onBlockedSelect={onBlockedSelect}
        runtimeContext={{ ...createEmptySovereignToolShortcutContext(), repoReady: true, repoFileCount: 4 }}
      />,
    );

    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    const diff = screen.getByRole('menuitem', { name: 'Diff' });
    expect(diff).not.toBeDisabled();
    expect(diff).toHaveAttribute('aria-disabled', 'false');
    expect(diff).toHaveAttribute('data-can-open', 'false');
    fireEvent.click(diff);

    expect(onBlockedSelect).toHaveBeenCalledWith('diff');
    expect(onSelect).not.toHaveBeenCalled();
    expect(useLauncherStore.getState().windows).toEqual([]);
  });

  it('blocks Diff and Executor without their required evidence', () => {
    const onSelect = vi.fn();
    render(
      <SovereignToolLauncher
        onSelect={onSelect}
        runtimeContext={{ ...createEmptySovereignToolShortcutContext(), repoReady: true, repoFileCount: 4, githubAccessState: 'ready', executorAvailable: true }}
      />,
    );

    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    expect(screen.getByRole('menuitem', { name: 'Diff' })).toBeDisabled();
    expect(screen.getByRole('menuitem', { name: 'Executor' })).toBeDisabled();
    expect(screen.getByText('Kein Diff')).toBeInTheDocument();
    expect(screen.getByText('Ausführungsauftrag fehlt')).toBeInTheDocument();
  });

  it('allows Executor only for a classified code or Draft-PR execution intent', () => {
    const onSelect = vi.fn();
    render(
      <SovereignToolLauncher
        onSelect={onSelect}
        runtimeContext={{
          ...createEmptySovereignToolShortcutContext(),
          repoReady: true,
          repoFileCount: 4,
          githubAccessState: 'ready',
          executorAvailable: true,
          hasExecutorMission: true,
          executorIntent: 'code_execution',
        }}
      />,
    );

    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    const executor = screen.getByRole('menuitem', { name: 'Executor' });
    expect(executor).toBeEnabled();
    fireEvent.click(executor);
    expect(onSelect).toHaveBeenCalledWith('executor');
  });

  it('opens core utility windows only after their inspection gate allows it', () => {
    const onSelect = vi.fn();
    render(<SovereignToolLauncher onSelect={onSelect} />);
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Settings' }));

    expect(onSelect).toHaveBeenCalledWith('settings');
    expect(useLauncherStore.getState().windows.some((entry) => entry.id === 'settings')).toBe(true);
  });

  it('shows stored inspection evidence after a core tool has produced a result', () => {
    useSovereignToolInspectionStore.getState().recordEvidence('health', {
      outcome: 'ready',
      statusLabel: 'Client-Checks bestanden',
      reason: 'Echte Client-Evidence vorhanden.',
      nextAction: 'CI separat prüfen.',
      observedAt: Date.now(),
    });
    render(<SovereignToolLauncher onSelect={vi.fn()} />);
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));

    const health = screen.getByRole('menuitem', { name: 'Health' });
    expect(health).toHaveAttribute('data-gate-state', 'ready');
    expect(screen.getByText('Client-Checks bestanden')).toBeInTheDocument();
  });

  it('downgrades stale inspection evidence instead of keeping a false ready state', () => {
    useSovereignToolInspectionStore.getState().recordEvidence('health', {
      outcome: 'ready',
      statusLabel: 'Client-Checks bestanden',
      reason: 'Alte Client-Evidence.',
      nextAction: 'Nichts tun.',
      observedAt: 1,
    });

    render(<SovereignToolLauncher onSelect={vi.fn()} />);
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));

    const health = screen.getByRole('menuitem', { name: 'Health' });
    expect(health).toHaveAttribute('data-gate-state', 'inspection');
    expect(screen.getByText('Erneut prüfen')).toBeInTheDocument();
    expect(health.getAttribute('title')).toContain('veraltet');
  });

  it('shows inspection status instead of pre-claiming health, memory or coverage', () => {
    render(<SovereignToolLauncher onSelect={vi.fn()} />);
    fireEvent.click(screen.getByLabelText('Tool Launcher öffnen'));

    for (const name of ['Health', 'Memory', 'Coverage']) {
      const item = screen.getByRole('menuitem', { name });
      expect(item).toHaveAttribute('data-gate-state', 'inspection');
      expect(item.getAttribute('title')).toContain('erst');
      expect(item.getAttribute('title')?.toLowerCase()).not.toContain('gesund');
    }
  });
});
