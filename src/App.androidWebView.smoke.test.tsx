// @vitest-environment jsdom

import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

vi.mock('./features/release/PlayReleaseChat', () => ({
  PlayReleaseChat: () => (
    <main data-testid="sovereign-release-chat" data-layout="play-release-chat" aria-label="Sovereign Chat">
      <textarea aria-label="Nachricht an Sovereign" />
      <button type="button" aria-label="Senden">↑</button>
    </main>
  ),
}));

vi.mock('./features/evidence-observatory/EvidenceObservatoryAtlas', () => ({
  EvidenceObservatoryAtlas: () => <main data-testid="evidence-observatory">Observatory</main>,
}));

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.replaceState({}, '', '/');
  delete window.__sovereignSetupState;
});

describe('Android Play release chat smoke', () => {
  it('boots directly into the focused chat surface', () => {
    render(<App />);

    expect(screen.getByTestId('sovereign-release-chat')).toHaveAttribute('data-layout', 'play-release-chat');
    expect(screen.getByLabelText('Sovereign Chat')).toBeDefined();
    expect(screen.getByLabelText('Nachricht an Sovereign')).toBeDefined();
    expect(screen.getByLabelText('Senden')).toBeDefined();
  });

  it('does not mount monitor or legacy operator controls in the Android release root', () => {
    render(<App />);

    expect(screen.queryByTestId('sovereign-monitor-app')).toBeNull();
    expect(screen.queryByTestId('live-workspace-monitor')).toBeNull();
    expect(screen.queryByTestId('operator-monitor')).toBeNull();
    expect(screen.queryByTestId('automation__mode-select')).toBeNull();
  });
});
