// @vitest-environment jsdom

import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./features/release/PlayReleaseChat', () => ({
  PlayReleaseChat: () => (
    <section data-testid="sovereign-release-chat" aria-label="Sovereign Play Release">
      <textarea aria-label="Nachricht an Sovereign" />
      <button type="button">Draft PR erstellen</button>
    </section>
  ),
}));
vi.mock('./features/evidence-observatory/EvidenceObservatoryAtlas', () => ({
  EvidenceObservatoryAtlas: () => <section data-testid="evidence-observatory-atlas">Observatory</section>,
}));

import App from './App';

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/');
  delete window.__sovereignSetupState;
});

describe('App Android WebView smoke', () => {
  it('enters the current-session release chat as the Android app surface', () => {
    render(<App />);

    const app = screen.getByTestId('sovereign-chat-app');
    expect(app).toHaveAttribute('data-layout', 'chat-first-agent-zero-background');
    expect(app).toHaveAttribute('data-primary-surface', 'play-release-chat');
    expect(app).toHaveAttribute('data-truth-scope', 'current-chat-session-only');
    expect(screen.getByTestId('sovereign-release-chat')).toBeDefined();
  });

  it('keeps the mission composer and Draft-PR action reachable on the mobile surface', () => {
    render(<App />);

    expect(screen.getByLabelText('Nachricht an Sovereign')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Draft PR erstellen' })).toBeDefined();
  });

  it('does not mount legacy builder/monitor truth surfaces during initial entry', () => {
    render(<App />);

    expect(screen.queryByTestId('builder-container')).toBeNull();
    expect(screen.queryByTestId('live-workspace-monitor-desktop')).toBeNull();
    expect(screen.queryByTestId('operator-monitor')).toBeNull();
  });
});
