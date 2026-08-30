import React from 'react';
import { Provider } from 'react-redux';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
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

describe('SovereignAppWrapper - Monitor-first UI Contract', () => {
  it('forwards directly into the App without a wrapper lamp shell', async () => {
    render(<Provider store={store}><SovereignAppWrapper /></Provider>);

    await waitFor(() => {
      expect(screen.getByTestId('builder-container')).toHaveAttribute(
        'data-layout',
        'live-desktop-monitor-primary',
      );
    });

    expect(screen.queryByTestId('sovereign-app-wrapper')).toBeNull();
    expect(screen.queryByTestId('sovereign-minimal-lamp-bar')).toBeNull();
    expect(screen.queryByTestId('sovereign-shell-content')).toBeNull();
  });

  it('keeps the workspace monitor and embedded LLM dock as the visible product surface', async () => {
    render(<Provider store={store}><SovereignAppWrapper /></Provider>);

    await waitFor(() => {
      expect(screen.getByTestId('live-workspace-monitor')).toBeDefined();
    });

    expect(screen.getByTestId('live-workspace-monitor-desktop')).toBeDefined();
    expect(screen.getByTestId('monitor-communication-dock')).toBeDefined();
    expect(screen.getByLabelText('Codeauftrag an Sovereign')).toBeDefined();
    expect(screen.queryByTestId('sovereign-chat-body-window')).toBeNull();
    expect(screen.getByLabelText('Sovereign Studio Tabs')).toBeDefined();
  });
});
