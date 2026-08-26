import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SovereignAppWrapper from './SovereignAppWrapper';

vi.mock('./features/release/PlayReleaseChat', () => ({
  PlayReleaseChat: () => (
    <main data-testid="sovereign-release-chat" data-layout="play-release-chat" aria-label="Sovereign Chat">
      Release chat
    </main>
  ),
}));

vi.mock('./features/evidence-observatory/EvidenceObservatoryAtlas', () => ({
  EvidenceObservatoryAtlas: () => <main data-testid="evidence-observatory">Observatory</main>,
}));

describe('SovereignAppWrapper - Play release chat contract', () => {
  it('forwards directly into App without an extra wrapper shell', () => {
    window.history.replaceState({}, '', '/');
    render(<SovereignAppWrapper />);

    expect(screen.getByTestId('sovereign-release-chat')).toHaveAttribute('data-layout', 'play-release-chat');
    expect(screen.queryByTestId('sovereign-app-wrapper')).toBeNull();
    expect(screen.queryByTestId('sovereign-minimal-lamp-bar')).toBeNull();
    expect(screen.queryByTestId('sovereign-shell-content')).toBeNull();
  });

  it('does not remount the deferred monitor surface', () => {
    window.history.replaceState({}, '', '/');
    render(<SovereignAppWrapper />);

    expect(screen.getByLabelText('Sovereign Chat')).toBeDefined();
    expect(screen.queryByTestId('live-workspace-monitor')).toBeNull();
    expect(screen.queryByTestId('sovereign-monitor-app')).toBeNull();
  });
});
