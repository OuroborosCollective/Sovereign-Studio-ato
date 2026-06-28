import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
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

describe('SovereignAppWrapper - Chat-First UI Contract', () => {
  it('renders a minimal lamp bar as the only visible shell', () => {
    render(<SovereignAppWrapper />);

    // The wrapper should render a minimal lamp bar
    expect(screen.getByTestId('sovereign-app-wrapper')).toBeDefined();
    expect(screen.getByTestId('sovereign-minimal-lamp-bar')).toBeDefined();

    // Should NOT render the old dominant runtime frame
    expect(screen.queryByText('Sovereign Runtime Frame')).toBeNull();

    // Should NOT render the 8-module bar
    expect(screen.queryByTestId('sovereign-wrapper-workspace-menu')).toBeNull();
  });

  it('contains the App content inside the minimal shell', () => {
    render(<SovereignAppWrapper />);

    // The app should render inside the shell
    expect(screen.getByTestId('sovereign-shell-content')).toBeDefined();
  });

  it('shows warning state in lamp bar when no repo loaded', () => {
    render(<SovereignAppWrapper />);

    // Should show 'warning' status when no repo is loaded
    expect(screen.getByText('warning')).toBeDefined();
  });

  it('shows DevChat workbench after opening the app', () => {
    render(<SovereignAppWrapper />);

    // Open the app
    fireEvent.click(screen.getByRole('button', { name: 'Sovereign Arbeitsfläche öffnen' }));

    // The DevChat workbench should now be visible
    expect(screen.getByTestId('builder-container')).toHaveAttribute('data-layout', 'devchat-replit');
    expect(screen.getByText('DevChat')).toBeDefined();
    expect(screen.getByLabelText(/Sovereign Chat Eingabe/i)).toBeDefined();
  });
});
