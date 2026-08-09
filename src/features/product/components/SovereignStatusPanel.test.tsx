import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import React from 'react';

import { SovereignStatusPanel, type SovereignStatusPanelProps } from './SovereignStatusPanel';

const READY_PROPS = {
  githubState: 'ready',
  executorAvailable: true,
  agentConfigured: true,
  patchRouteAvailable: true,
  repoReady: true,
} satisfies SovereignStatusPanelProps;

describe('SovereignStatusPanel accessibility', () => {
  it('exposes count-aware German descriptions as native tooltips and accessible names', () => {
    const { rerender } = render(
      <SovereignStatusPanel
        {...READY_PROPS}
        blockerCounts={{ activeBlockers: 0, warnings: 0, errors: 0 }}
      />,
    );

    expect(screen.getByRole('status', { name: 'Keine aktiven Blocker' }))
      .toHaveAttribute('title', 'Keine aktiven Blocker');
    expect(screen.getByRole('status', { name: 'Keine Warnungen' }))
      .toHaveAttribute('title', 'Keine Warnungen');
    expect(screen.getByRole('status', { name: 'Keine Fehler' }))
      .toHaveAttribute('title', 'Keine Fehler');

    rerender(
      <SovereignStatusPanel
        {...READY_PROPS}
        blockerCounts={{ activeBlockers: 1, warnings: 1, errors: 1 }}
      />,
    );

    expect(screen.getByRole('status', { name: '1 aktiver Blocker' }))
      .toHaveAttribute('title', '1 aktiver Blocker');
    expect(screen.getByRole('status', { name: '1 Warnung' }))
      .toHaveAttribute('title', '1 Warnung');
    expect(screen.getByRole('status', { name: '1 Fehler' }))
      .toHaveAttribute('title', '1 Fehler');

    rerender(
      <SovereignStatusPanel
        {...READY_PROPS}
        blockerCounts={{ activeBlockers: 3, warnings: 4, errors: 5 }}
      />,
    );

    expect(screen.getByRole('status', { name: '3 aktive Blocker' }))
      .toHaveAttribute('title', '3 aktive Blocker');
    expect(screen.getByRole('status', { name: '4 Warnungen' }))
      .toHaveAttribute('title', '4 Warnungen');
    expect(screen.getByRole('status', { name: '5 Fehler' }))
      .toHaveAttribute('title', '5 Fehler');
  });

  it('describes ready and blocked sub-statuses without relying on color', () => {
    const { rerender } = render(<SovereignStatusPanel {...READY_PROPS} />);

    expect(screen.getByRole('status', { name: 'Repository ist bereit' }))
      .toHaveAttribute('title', 'Repository ist bereit');
    expect(screen.getByRole('status', { name: 'GitHub-Verbindung ist bereit' }))
      .toHaveAttribute('title', 'GitHub-Verbindung ist bereit');
    expect(screen.getByRole('status', { name: 'Patch-Route ist bereit' }))
      .toHaveAttribute('title', 'Patch-Route ist bereit');
    expect(screen.getByRole('status', { name: 'Draft PR ist vorhanden und bereit' }))
      .toHaveAttribute('title', 'Draft PR ist vorhanden und bereit');

    rerender(
      <SovereignStatusPanel
        {...READY_PROPS}
        githubState="blocked"
        patchRouteAvailable={false}
        repoReady={false}
      />,
    );

    expect(screen.getByRole('status', { name: 'Repository ist nicht bereit' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'GitHub-Verbindung ist nicht bereit' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Patch-Route ist nicht bereit' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Draft PR fehlt oder ist nicht bereit' })).toBeInTheDocument();
  });

  it('labels the panel region and the recommended action', () => {
    render(
      <SovereignStatusPanel
        {...READY_PROPS}
        customNextAction="Bereit für den ersten Auftrag"
      />,
    );

    expect(screen.getByRole('region', { name: 'Sovereign Runtime-Status' })).toBeInTheDocument();
    expect(screen.getByRole('status', {
      name: 'Nächste empfohlene Aktion: Bereit für den ersten Auftrag',
    })).toHaveAttribute(
      'title',
      'Nächste empfohlene Aktion: Bereit für den ersten Auftrag',
    );
  });

  it('exposes the compact summary through the same accessible status contract', () => {
    render(
      <SovereignStatusPanel
        {...READY_PROPS}
        compact
        blockerCounts={{ activeBlockers: 2, warnings: 1, errors: 0 }}
      />,
    );

    expect(screen.getByRole('status', {
      name: '2 Blocker · 1 Warnungen · 0 Fehler',
    })).toHaveAttribute('title', '2 Blocker · 1 Warnungen · 0 Fehler');
  });
});
