import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('./features/control-surface-vnext/App', () => ({
  default: () => <section data-testid="sovereign-control-surface-vnext">Control surface vNext</section>,
}));
vi.mock('./features/evidence-observatory/EvidenceObservatoryAtlas', () => ({
  EvidenceObservatoryAtlas: () => <section data-testid="evidence-observatory-atlas">Observatory</section>,
}));

import App from './App';

describe('App', () => {
  it('opens the runtime-readback vNext control surface as the default surface', () => {
    render(<App />);

    const app = screen.getByTestId('sovereign-chat-app');
    expect(app).toHaveAttribute('data-layout', 'sovereign-control-surface-vnext');
    expect(app).toHaveAttribute('data-primary-surface', 'sovereign-control-surface-vnext');
    expect(app).toHaveAttribute('data-truth-scope', 'runtime-readback-only');
    expect(app).toHaveAttribute('aria-label', 'Sovereign Control Surface');
    expect(screen.getByTestId('sovereign-control-surface-vnext')).toBeDefined();
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
