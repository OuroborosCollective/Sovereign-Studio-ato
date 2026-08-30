import React from 'react';
import { Provider } from 'react-redux';
import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import App from './App';
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

describe('App', () => {
  it('opens the permanent monitor-first workspace surface', async () => {
    render(<Provider store={store}><App /></Provider>);

    expect(screen.getByTestId('sovereign-monitor-app')).toHaveAttribute(
      'data-layout',
      'monitor-first-live-workspace',
    );
    expect(screen.getByTestId('sovereign-monitor-app')).toHaveAttribute(
      'data-legacy-backend-image-marker',
      'DevChat sovereign-release-chat play-release-chat',
    );
    expect(screen.queryByText('DevChat')).toBeNull();
    expect(await screen.findAllByText('Monitor')).not.toHaveLength(0);
    expect(screen.getByTestId('builder-container')).toHaveAttribute(
      'data-layout',
      'live-desktop-monitor-primary',
    );
    expect(screen.getByTestId('sovereign-live-monitor-primary')).toBeDefined();
    expect(screen.getByTestId('live-workspace-monitor')).toBeDefined();
    expect(screen.getByTestId('live-workspace-monitor-desktop')).toBeDefined();
    expect(screen.getByTestId('monitor-communication-dock')).toBeDefined();
    expect(screen.getByLabelText('Frage an Sovereign während Live Monitor')).toBeDefined();
    expect(screen.queryByTestId('sovereign-chat-body-window')).toBeNull();
    expect(screen.queryByTestId('chat-only-app')).toBeNull();
    expect(screen.queryByLabelText('Sovereign Rescue öffnen')).toBeNull();
  });
});
