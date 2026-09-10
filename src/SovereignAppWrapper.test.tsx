import React from 'react';
import { Provider } from 'react-redux';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('./features/control-surface-vnext/App', () => ({
  default: () => (
    <section data-testid="sovereign-control-surface-vnext">
      <textarea aria-label="Mission an Sovereign" />
      <nav aria-label="Sovereign mobile projections" />
    </section>
  ),
}));

import SovereignAppWrapper from './SovereignAppWrapper';
import { store } from './store';

beforeAll(() => {
  const cryptoMock = {
    randomUUID: () => 'test-uuid',
  };

  if (!globalThis.crypto) {
    Object.defineProperty(globalThis, 'crypto', {
      value: cryptoMock,
      configurable: true,
    });
    return;
  }

  if (!globalThis.crypto.randomUUID) {
    Object.defineProperty(globalThis.crypto, 'randomUUID', {
      value: cryptoMock.randomUUID,
      configurable: true,
    });
  }
});

describe('SovereignAppWrapper - vNext runtime-readback UI contract', () => {
  it('forwards directly into the vNext control surface without a wrapper lamp shell', async () => {
    render(<Provider store={store}><SovereignAppWrapper /></Provider>);

    await waitFor(() => {
      expect(screen.getByTestId('sovereign-chat-app')).toHaveAttribute(
        'data-primary-surface',
        'sovereign-control-surface-vnext',
      );
    });

    expect(screen.getByTestId('sovereign-chat-app')).toHaveAttribute(
      'data-truth-scope',
      'runtime-readback-only',
    );
    expect(screen.getByTestId('sovereign-control-surface-vnext')).toBeDefined();
    expect(screen.queryByTestId('sovereign-app-wrapper')).toBeNull();
    expect(screen.queryByTestId('sovereign-minimal-lamp-bar')).toBeNull();
    expect(screen.queryByTestId('sovereign-shell-content')).toBeNull();
    expect(screen.queryByTestId('builder-container')).toBeNull();
  });

  it('keeps the vNext mission composer visible without resurrecting the old route-picker shell', async () => {
    render(<Provider store={store}><SovereignAppWrapper /></Provider>);

    await waitFor(() => {
      expect(screen.getByTestId('sovereign-control-surface-vnext')).toBeDefined();
    });

    expect(screen.getByLabelText('Mission an Sovereign')).toBeDefined();
    expect(screen.queryByLabelText('LLM Route')).toBeNull();
    expect(screen.queryByLabelText('Sovereign Hauptmenü')).toBeNull();
    expect(screen.queryByTestId('live-workspace-monitor-desktop')).toBeNull();
    expect(screen.queryByTestId('monitor-communication-dock')).toBeNull();
    expect(screen.queryByLabelText('Sovereign Studio Tabs')).toBeNull();
  });
});
