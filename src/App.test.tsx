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

  it('opens the no-code chat workbench after launch while keeping repo setup available', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'Sovereign Arbeitsfläche öffnen' }));

    expect(screen.getByText('Sovereign Canvas Tool')).toBeDefined();
    expect(screen.getByText('Automation Mode')).toBeDefined();

    expect(screen.getByRole('tab', { name: 'Open Repo tab' })).toBeDefined();
    expect(screen.getByRole('tab', { name: 'Open Chat tab' })).toBeDefined();
    expect(screen.getByTestId('tabbar__more-select')).toBeDefined();

    expect(screen.getByText('Sovereign Chat')).toBeDefined();
    expect(screen.getByText('OpenHands Runtime')).toBeDefined();
    expect(screen.getByPlaceholderText(/What do you want to build/)).toBeDefined();

    fireEvent.click(screen.getByRole('tab', { name: 'Open Repo tab' }));
    expect(screen.getByPlaceholderText('https://github.com/owner/repository')).toBeDefined();
  });
});
