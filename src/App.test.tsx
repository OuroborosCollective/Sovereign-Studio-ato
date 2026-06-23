import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
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
  it('renders a clear launch screen initially', () => {
    render(<App />);

    expect(screen.getByText('Sovereign Arbeitsfläche öffnen')).toBeDefined();
    expect(screen.getByText(/Ohne geladenes Repository bleibt Full Auto bewusst blockiert/)).toBeDefined();
  });

  it('opens the repo-first container workspace after launch', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'Sovereign Arbeitsfläche öffnen' }));

    expect(screen.getByText('Sovereign Canvas Tool')).toBeDefined();
    expect(screen.getByText('Automation Mode')).toBeDefined();

    // Tab buttons now use role="tab" with aria-label for accessibility
    // Primary tabs are visible as buttons; secondary tabs are in "Mehr Bereiche" dropdown
    expect(screen.getByRole('tab', { name: 'Open Repo tab' })).toBeDefined();
    expect(screen.getByRole('tab', { name: 'Open Builder tab' })).toBeDefined();
    // Secondary tabs (Remote Memory, Pattern Memory, Telemetry) are in the dropdown
    expect(screen.getByTestId('tabbar__more-select')).toBeDefined();

    expect(screen.getByPlaceholderText('https://github.com/owner/repository')).toBeDefined();
  });
});
