import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { SovereignStatusPanel } from './SovereignStatusPanel';

describe('SovereignStatusPanel Accessibility and Hover Tooltips', () => {
  it('renders correct state-dependent title tooltips for StatusChip components', () => {
    // 1. With counts = 0
    const { rerender } = render(
      <SovereignStatusPanel
        githubState="ready"
        executorAvailable={true}
        agentConfigured={true}
        patchRouteAvailable={true}
        repoReady={true}
        blockerCounts={{ activeBlockers: 0, warnings: 0, errors: 0 }}
      />
    );

    const blockerChip = screen.getByText(/Blocker/);
    const warningsChip = screen.getByText(/Warnungen/);
    const errorsChip = screen.getByText(/Fehler/);

    expect(blockerChip).toHaveAttribute('title', 'Keine aktiven Blocker');
    expect(warningsChip).toHaveAttribute('title', 'Keine Warnungen');
    expect(errorsChip).toHaveAttribute('title', 'Keine Fehler');

    // 2. With count = 1
    rerender(
      <SovereignStatusPanel
        githubState="ready"
        executorAvailable={true}
        agentConfigured={true}
        patchRouteAvailable={true}
        repoReady={true}
        blockerCounts={{ activeBlockers: 1, warnings: 1, errors: 1 }}
      />
    );

    expect(screen.getByText(/1 Blocker/)).toHaveAttribute('title', '1 aktiver Blocker');
    expect(screen.getByText(/1 Warnungen/)).toHaveAttribute('title', '1 Warnung');
    expect(screen.getByText(/1 Fehler/)).toHaveAttribute('title', '1 Fehler');

    // 3. With counts > 1
    rerender(
      <SovereignStatusPanel
        githubState="ready"
        executorAvailable={true}
        agentConfigured={true}
        patchRouteAvailable={true}
        repoReady={true}
        blockerCounts={{ activeBlockers: 3, warnings: 4, errors: 5 }}
      />
    );

    expect(screen.getByText(/3 Blocker/)).toHaveAttribute('title', '3 aktive Blocker');
    expect(screen.getByText(/4 Warnungen/)).toHaveAttribute('title', '4 Warnungen');
    expect(screen.getByText(/5 Fehler/)).toHaveAttribute('title', '5 Fehler');
  });

  it('renders correct state-dependent title tooltips for SubStatus components', () => {
    // 1. All ready = true
    const { rerender } = render(
      <SovereignStatusPanel
        githubState="ready"
        executorAvailable={true}
        agentConfigured={true}
        patchRouteAvailable={true}
        repoReady={true}
      />
    );

    expect(screen.getByText('Repo bereit')).toHaveAttribute('title', 'Repository ist bereit');
    expect(screen.getByText('GitHub bereit')).toHaveAttribute('title', 'GitHub-Verbindung ist bereit');
    expect(screen.getByText('Patch-Route')).toHaveAttribute('title', 'Patch-Route ist bereit');
    expect(screen.getByText('Draft PR')).toHaveAttribute('title', 'Draft PR ist vorhanden und bereit');

    // 2. All ready = false / blocked
    rerender(
      <SovereignStatusPanel
        githubState="blocked"
        executorAvailable={false}
        agentConfigured={false}
        patchRouteAvailable={false}
        repoReady={false}
      />
    );

    expect(screen.getByText('Repo bereit')).toHaveAttribute('title', 'Repository ist nicht bereit');
    expect(screen.getByText('GitHub bereit')).toHaveAttribute('title', 'GitHub-Verbindung ist nicht bereit');
    expect(screen.getByText('Patch-Route')).toHaveAttribute('title', 'Patch-Route ist nicht bereit');
    expect(screen.getByText('Draft PR')).toHaveAttribute('title', 'Draft PR fehlt oder ist nicht bereit');
  });

  it('renders correct Next Action title tooltip', () => {
    render(
      <SovereignStatusPanel
        githubState="ready"
        executorAvailable={true}
        agentConfigured={true}
        patchRouteAvailable={true}
        repoReady={true}
        customNextAction="Bereit für den ersten Auftrag"
      />
    );

    const nextActionContainer = screen.getByText('Nächste Aktion').closest('[title]');
    expect(nextActionContainer).toHaveAttribute('title', 'Nächste empfohlene Aktion: Bereit für den ersten Auftrag');
  });
});
