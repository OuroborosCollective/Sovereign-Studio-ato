// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
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
    // Use a properly formatted GitHub PAT (30+ chars after ghp_)
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

    // Should render without crashing, no error UI should show since no error occurred
    expect(document.body.textContent).toBe('');
  });
});