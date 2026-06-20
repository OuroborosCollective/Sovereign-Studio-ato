// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { SovereignTabErrorBoundary } from './SovereignTabErrorBoundary';

const ThrowError = ({ message = 'Test error' }: { message?: string }) => {
  throw new Error(message);
};

describe('SovereignTabErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders children when no error occurs', () => {
    render(
      <SovereignTabErrorBoundary tabId="test" tabLabel="Test Tab">
        <div data-testid="child">Content</div>
      </SovereignTabErrorBoundary>
    );

    expect(screen.getByTestId('child')).toBeDefined();
    expect(screen.getByText('Content')).toBeDefined();
  });

  it('catches errors and displays error state', () => {
    render(
      <SovereignTabErrorBoundary tabId="crash" tabLabel="Crash Tab">
        <ThrowError />
      </SovereignTabErrorBoundary>
    );

    expect(screen.getByText(/Crash Tab.*tab crashed/)).toBeDefined();
    expect(screen.getByText(/Test error/i)).toBeDefined();
  });

  it('shows dismiss button when onDismiss is provided', () => {
    const onDismiss = vi.fn();

    render(
      <SovereignTabErrorBoundary tabId="dismissible" tabLabel="Dismissible" onDismiss={onDismiss}>
        <ThrowError message="Dismissable error" />
      </SovereignTabErrorBoundary>
    );

    const dismissButton = screen.getByRole('button', { name: 'Dismiss error' });
    expect(dismissButton).toBeDefined();

    dismissButton.click();
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('does not show dismiss button when onDismiss is not provided', () => {
    render(
      <SovereignTabErrorBoundary tabId="no-dismiss" tabLabel="No Dismiss">
        <ThrowError />
      </SovereignTabErrorBoundary>
    );

    expect(screen.queryByRole('button', { name: 'Dismiss error' })).toBeNull();
  });

  it('masks secrets in error messages', () => {
    const secret = 'ghp_1234567890abcdefghijklmnopqrstuvwx';

    render(
      <SovereignTabErrorBoundary tabId="secret-tab" tabLabel="Secret Tab">
        <ThrowError message={`Auth failed: ${secret}`} />
      </SovereignTabErrorBoundary>
    );

    const errorText = screen.getByText(/Auth failed:.*/i).textContent || '';
    expect(errorText).toContain('ghp_****');
    expect(errorText).not.toContain(secret);
  });

  it('displays alert icon for error state', () => {
    render(
      <SovereignTabErrorBoundary tabId="alert-test" tabLabel="Alert Test">
        <ThrowError />
      </SovereignTabErrorBoundary>
    );

    const alertIcon = document.querySelector('svg');
    expect(alertIcon).toBeDefined();
  });

  it('renders without children when no children provided', () => {
    render(
      <SovereignTabErrorBoundary tabId="empty" tabLabel="Empty Tab" />
    );

    expect(document.body.textContent).toBe('');
  });

  it('opens the tab circuit when the configured threshold is reached', () => {
    render(
      <SovereignTabErrorBoundary
        tabId="circuit"
        tabLabel="Circuit Tab"
        policy={{ failureThreshold: 1, cooldownMs: 30_000, halfOpenMaxAttempts: 1 }}
      >
        <ThrowError message="Circuit failure" />
      </SovereignTabErrorBoundary>
    );

    const fallback = screen.getByTestId('sovereign-tab-error-boundary');
    expect(fallback.getAttribute('data-tab-id')).toBe('circuit');
    expect(fallback.getAttribute('data-circuit-phase')).toBe('open');
    expect(screen.getByRole('button', { name: 'Retry tab' })).toBeDefined();
  });
});
