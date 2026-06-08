import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import App from './App';
import React from 'react';

// Mock crypto.randomUUID
if (!global.crypto) {
  (global as any).crypto = {
    randomUUID: () => 'test-uuid',
  };
}

describe('App', () => {
  it('renders login button initially', () => {
    render(<App />);
    expect(screen.getByText('Login')).toBeDefined();
  });

  it('renders main content after login', () => {
    render(<App />);
    const loginButton = screen.getByText('Login');
    fireEvent.click(loginButton);
    expect(screen.getByText('Sovereign Canvas Tool')).toBeDefined();
  });
});
