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

describe('SovereignAppWrapper - current-session chat-first UI contract', () => {
  it('forwards directly into the Play Release App without a wrapper lamp shell', async () => {
    render(<Provider store={store}><SovereignAppWrapper /></Provider>);

    await waitFor(() => {
      expect(screen.getByTestId('sovereign-chat-app')).toHaveAttribute(
        'data-primary-surface',
        'play-release-chat',
      );
    });

    expect(screen.getByTestId('sovereign-chat-app')).toHaveAttribute(
      'data-truth-scope',
      'current-chat-session-only',
    );
    expect(screen.getByTestId('sovereign-release-chat')).toHaveAttribute(
      'data-layout',
      'play-release-chat',
    );
    expect(screen.queryByTestId('sovereign-app-wrapper')).toBeNull();
    expect(screen.queryByTestId('sovereign-minimal-lamp-bar')).toBeNull();
    expect(screen.queryByTestId('sovereign-shell-content')).toBeNull();
    expect(screen.queryByTestId('builder-container')).toBeNull();
  });

  it('keeps the current-session composer, route picker, and main menu as the visible product surface', async () => {
    render(<Provider store={store}><SovereignAppWrapper /></Provider>);

    await waitFor(() => {
      expect(screen.getByTestId('sovereign-release-chat')).toBeDefined();
    });

    expect(screen.getByLabelText('Nachricht an Sovereign')).toBeDefined();
    expect(screen.getByLabelText('LLM Route')).toBeDefined();
    expect(screen.getByLabelText('Sovereign Hauptmenü')).toBeDefined();
    expect(screen.queryByTestId('live-workspace-monitor-desktop')).toBeNull();
    expect(screen.queryByTestId('monitor-communication-dock')).toBeNull();
    expect(screen.queryByLabelText('Sovereign Studio Tabs')).toBeNull();
  });
});
