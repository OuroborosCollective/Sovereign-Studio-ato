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

describe('SovereignAppWrapper - Chat-first UI Contract', () => {
  it('forwards directly into the App without a wrapper lamp shell', async () => {
    render(<Provider store={store}><SovereignAppWrapper /></Provider>);

    await waitFor(() => {
      expect(screen.getByTestId('builder-container')).toHaveAttribute(
        'data-layout',
        'chat-primary-agent-zero-background',
      );
    });

    expect(screen.queryByTestId('sovereign-app-wrapper')).toBeNull();
    expect(screen.queryByTestId('sovereign-minimal-lamp-bar')).toBeNull();
    expect(screen.queryByTestId('sovereign-shell-content')).toBeNull();
  });

  it('keeps the normal chat and model/tool dock as the visible product surface', async () => {
    render(<Provider store={store}><SovereignAppWrapper /></Provider>);

    await waitFor(() => {
      expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    });

    expect(screen.queryByTestId('live-workspace-monitor-desktop')).toBeNull();
    expect(screen.getByTestId('sovereign-chat-dock')).toBeDefined();
    expect(screen.getByLabelText('Codeauftrag an Sovereign')).toBeDefined();
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(screen.getByLabelText('Sovereign Studio Tabs')).toBeDefined();
  });
});
