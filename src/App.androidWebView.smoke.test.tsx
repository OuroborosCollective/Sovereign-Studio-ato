// @vitest-environment jsdom

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import App from './App';

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

async function openChatOnlyWorkspace(): Promise<void> {
  render(<App />);

  await waitFor(() => {
    expect(screen.getByTestId('builder-container')).toHaveAttribute(
      'data-layout',
      'devchat-appcontrol-integrated',
    );
  });
}

describe('App setup flow smoke', () => {
  it('enters the chat-only workbench as the app surface', async () => {
    render(<App />);

    expect(screen.getByTestId('chat-only-app')).toHaveAttribute(
      'data-layout',
      'chat-only-live-entry',
    );

    await waitFor(() => {
      expect(screen.getByTestId('builder-container')).toHaveAttribute(
        'data-layout',
        'devchat-appcontrol-integrated',
      );
    });
  });

  it('keeps the Builder chat available on Android', async () => {
    await openChatOnlyWorkspace();

    expect(screen.getByText('DevChat')).toBeDefined();
    expect(screen.getByLabelText(/Sovereign Chat Eingabe/i)).toBeDefined();
    expect(screen.getByPlaceholderText(/GitHub URL oder Auftrag/)).toBeDefined();
  });

  it('does not open legacy controls during initial chat entry', async () => {
    await openChatOnlyWorkspace();

    expect(screen.queryByTestId('operator-monitor')).toBeNull();
    expect(screen.queryByTestId('automation__mode-select')).toBeNull();
    expect(screen.queryByPlaceholderText('https://github.com/owner/repository')).toBeNull();
  });
});
