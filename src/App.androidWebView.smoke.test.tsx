// @vitest-environment jsdom

import React from 'react';
import { Provider } from 'react-redux';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
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

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  delete window.__sovereignSetupState;
});

async function openMonitorWorkspace(): Promise<void> {
  render(<Provider store={store}><App /></Provider>);

  await waitFor(() => {
    expect(screen.getByTestId('builder-container')).toHaveAttribute(
      'data-layout',
      'live-desktop-monitor-primary',
    );
  });
}

describe('App setup flow smoke', () => {
  it('enters the monitor-first workbench as the Android app surface', async () => {
    render(<Provider store={store}><App /></Provider>);

    expect(screen.getByTestId('sovereign-monitor-app')).toHaveAttribute(
      'data-layout',
      'monitor-first-live-workspace',
    );

    await waitFor(() => {
      expect(screen.getByTestId('builder-container')).toHaveAttribute(
        'data-layout',
        'live-desktop-monitor-primary',
      );
    });
    expect(screen.getByTestId('live-workspace-monitor-desktop')).toBeDefined();
  });

  it('keeps LLM communication inside the Android monitor without a chat surface', async () => {
    await openMonitorWorkspace();

    expect(screen.getByTestId('monitor-communication-dock')).toBeDefined();
    expect(screen.getByLabelText('Codeauftrag an Sovereign')).toBeDefined();
    expect(screen.getByPlaceholderText(/Codeauftrag eingeben/i)).toBeDefined();
    expect(screen.queryByTestId('sovereign-chat-body-window')).toBeNull();
  });

  it('does not open legacy controls during initial chat entry', async () => {
    await openMonitorWorkspace();

    expect(screen.queryByTestId('operator-monitor')).toBeNull();
    expect(screen.queryByTestId('automation__mode-select')).toBeNull();
    expect(screen.queryByPlaceholderText('https://github.com/owner/repository')).toBeNull();
  });
});
