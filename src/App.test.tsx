import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

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

describe('App', () => {
  it('opens the focused Play release chat instead of the unfinished monitor', () => {
    window.history.replaceState({}, '', '/');
    render(<App />);

    expect(screen.getByTestId('sovereign-release-chat')).toHaveAttribute('data-layout', 'play-release-chat');
    expect(screen.getByLabelText('Sovereign Chat')).toBeDefined();
    expect(screen.queryByTestId('sovereign-monitor-app')).toBeNull();
    expect(screen.queryByTestId('live-workspace-monitor')).toBeNull();
  });

  it('keeps the evidence observatory route available without exposing the monitor shell', () => {
    window.history.replaceState({}, '', '/observatory');
    render(<App />);

    expect(screen.getByTestId('evidence-observatory')).toBeDefined();
    expect(screen.queryByTestId('sovereign-release-chat')).toBeNull();
  });
});
