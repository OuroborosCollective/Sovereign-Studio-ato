import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('./features/release/PlayReleaseChat', () => ({
  PlayReleaseChat: () => <section data-testid="sovereign-release-chat">Release chat</section>,
}));
vi.mock('./features/evidence-observatory/EvidenceObservatoryAtlas', () => ({
  EvidenceObservatoryAtlas: () => <section data-testid="evidence-observatory-atlas">Observatory</section>,
}));

import App from './App';

describe('App', () => {
  it('opens the current-session Play Release chat as the default surface', () => {
    render(<App />);

    const app = screen.getByTestId('sovereign-chat-app');
    expect(app).toHaveAttribute('data-layout', 'chat-first-agent-zero-background');
    expect(app).toHaveAttribute('data-primary-surface', 'play-release-chat');
    expect(app).toHaveAttribute('data-truth-scope', 'current-chat-session-only');
    expect(screen.getByTestId('sovereign-release-chat')).toBeDefined();
    expect(screen.queryByTestId('evidence-observatory-atlas')).toBeNull();
  });

  it('keeps the evidence observatory on its explicit route', () => {
    window.history.pushState({}, '', '/observatory');
    render(<App />);

    expect(screen.getByTestId('evidence-observatory-atlas')).toBeDefined();
    expect(screen.queryByTestId('sovereign-chat-app')).toBeNull();
    window.history.pushState({}, '', '/');
  });
});
