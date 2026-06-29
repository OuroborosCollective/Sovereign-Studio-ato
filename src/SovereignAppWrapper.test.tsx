import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import SovereignAppWrapper from './SovereignAppWrapper';

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

describe('SovereignAppWrapper - Chat-only UI Contract', () => {
  it('forwards directly into the App without a wrapper lamp shell', async () => {
    render(<SovereignAppWrapper />);

    await waitFor(() => {
      expect(screen.getByTestId('builder-container')).toHaveAttribute(
        'data-layout',
        'devchat-appcontrol-integrated',
      );
    });

    expect(screen.queryByTestId('sovereign-app-wrapper')).toBeNull();
    expect(screen.queryByTestId('sovereign-minimal-lamp-bar')).toBeNull();
    expect(screen.queryByTestId('sovereign-shell-content')).toBeNull();
  });

  it('keeps the AppControl DevChat workbench as the visible product surface', async () => {
    render(<SovereignAppWrapper />);

    await waitFor(() => {
      expect(screen.getByText('DevChat')).toBeDefined();
    });

    expect(screen.getByLabelText(/Sovereign Chat Eingabe/i)).toBeDefined();
    expect(screen.getByLabelText('Sovereign Studio Tabs')).toBeDefined();
  });
});
