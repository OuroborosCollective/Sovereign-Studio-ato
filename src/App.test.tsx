import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
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

describe('App', () => {
  it('opens the chat-only live workbench', async () => {
    render(<App />);

    expect(screen.getByTestId('chat-only-app')).toHaveAttribute(
      'data-layout',
      'chat-only-live-entry',
    );
    expect(await screen.findByText('DevChat')).toBeDefined();
    expect(screen.getByTestId('builder-container')).toHaveAttribute(
      'data-layout',
      'devchat-appcontrol-integrated',
    );
    expect(screen.getByLabelText(/Sovereign Chat Eingabe/i)).toBeDefined();
    expect(screen.getByPlaceholderText(/GitHub URL oder Auftrag/)).toBeDefined();
  });
});
