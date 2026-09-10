// @vitest-environment jsdom

import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./features/control-surface-vnext/App', () => ({
  default: () => (
    <section data-testid="sovereign-control-surface-vnext" aria-label="Sovereign Control Surface vNext">
      <textarea aria-label="Mission an Sovereign" />
      <nav data-testid="mobile-bottom-nav">
        <button type="button">COMMAND</button>
        <button type="button">EVIDENCE</button>
        <button type="button">WORKSPACE</button>
        <button type="button">PUBLISH</button>
      </nav>
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
  it('enters the runtime-readback vNext control surface as the Android app surface', () => {
    render(<App />);

    const app = screen.getByTestId('sovereign-chat-app');
    expect(app).toHaveAttribute('data-layout', 'sovereign-control-surface-vnext');
    expect(app).toHaveAttribute('data-primary-surface', 'sovereign-control-surface-vnext');
    expect(app).toHaveAttribute('data-truth-scope', 'runtime-readback-only');
    expect(screen.getByTestId('sovereign-control-surface-vnext')).toBeDefined();
  });

  it('keeps the mission composer and fixed mobile projections reachable without exposing publication before a gate', () => {
    render(<App />);

    expect(screen.getByLabelText('Mission an Sovereign')).toBeDefined();
    expect(screen.getByTestId('mobile-bottom-nav')).toBeDefined();
    expect(screen.getByRole('button', { name: 'COMMAND' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'PUBLISH' })).toBeDefined();
    expect(screen.queryByRole('button', { name: 'CREATE DRAFT PR' })).toBeNull();
  });

  it('does not mount legacy builder/monitor truth surfaces during initial entry', () => {
    render(<App />);

    expect(screen.queryByTestId('builder-container')).toBeNull();
    expect(screen.queryByTestId('live-workspace-monitor-desktop')).toBeNull();
    expect(screen.queryByTestId('operator-monitor')).toBeNull();
  });
});
