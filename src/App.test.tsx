import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';
import React from 'react';

if (!global.crypto) {
  (global as any).crypto = {
    randomUUID: () => 'test-uuid',
  };
}

describe('App', () => {
  it('renders a clear launch screen initially', () => {
    render(<App />);
    expect(screen.getByText('Sovereign Canvas Tool')).toBeDefined();
    expect(screen.getByText('Sovereign Arbeitsfläche öffnen')).toBeDefined();
    expect(screen.getByText(/Ohne geladenes Repository bleibt Full Auto bewusst blockiert/)).toBeDefined();
  });

  it('opens the repo-first container workspace after launch', () => {
    render(<App />);
    fireEvent.click(screen.getByText('Sovereign Arbeitsfläche öffnen'));

    expect(screen.getByText('Automation Mode')).toBeDefined();
    expect(screen.getByText('Repo')).toBeDefined();
    expect(screen.getByText('Builder')).toBeDefined();
    expect(screen.getByText('Remote Memory')).toBeDefined();
    expect(screen.getByText('Pattern Memory')).toBeDefined();
    expect(screen.getByText('Telemetry')).toBeDefined();
    expect(screen.getByPlaceholderText('GitHub Repo URL')).toBeDefined();
  });
});
