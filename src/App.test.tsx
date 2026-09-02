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
  it('opens the permanent chat-first workspace surface', async () => {
    render(<Provider store={store}><App /></Provider>);

    expect(screen.getByTestId('sovereign-chat-app')).toHaveAttribute(
      'data-layout',
      'chat-first-agent-zero-background',
    );
    expect(screen.getByTestId('sovereign-chat-app')).toHaveAttribute(
      'data-legacy-backend-image-marker',
      'DevChat sovereign-release-chat play-release-chat',
    );
    expect(screen.queryByText('DevChat')).toBeNull();
    expect(await screen.findAllByText('Chat')).not.toHaveLength(0);
    expect(screen.getByTestId('builder-container')).toHaveAttribute(
      'data-layout',
      'chat-primary-agent-zero-background',
    );
    expect(screen.getByTestId('sovereign-chat-primary')).toBeDefined();
    expect(screen.queryByTestId('live-workspace-monitor')).toBeNull();
    expect(screen.queryByTestId('live-workspace-monitor-desktop')).toBeNull();
    expect(screen.getByTestId('sovereign-chat-dock')).toBeDefined();
    expect(screen.getByLabelText('Codeauftrag an Sovereign')).toBeDefined();
    expect(screen.getByTestId('sovereign-chat-body-window')).toBeDefined();
    expect(screen.queryByTestId('chat-only-app')).toBeNull();
    expect(screen.queryByLabelText('Sovereign Rescue öffnen')).toBeNull();
  });
});
