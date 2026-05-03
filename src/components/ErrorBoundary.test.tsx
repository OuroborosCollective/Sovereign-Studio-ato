// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { ErrorBoundary } from './ErrorBoundary';
import { storageService } from '../../services/storageService';

// Mock storageService
vi.mock('../../services/storageService', () => {
  return {
    storageService: {
      get: vi.fn(),
      set: vi.fn(),
    }
  };
});

const ThrowError = ({ message = 'Test error' }: { message?: string }) => {
  throw new Error(message);
};

describe('ErrorBoundary', () => {
  const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    consoleErrorSpy.mockClear();
  });

  it('should catch errors and display fallback UI', () => {
    render(
      <ErrorBoundary fallback={<div data-testid="fallback">Custom Fallback</div>}>
        <ThrowError />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('fallback')).toBeDefined();
    expect(screen.getByText('Custom Fallback')).toBeDefined();
  });

  it('swallows storageService.get error silently', async () => {
    vi.mocked(storageService.get).mockRejectedValueOnce(new Error('Storage get failure'));

    render(
      <ErrorBoundary>
        <ThrowError message="Error 1" />
      </ErrorBoundary>
    );

    await waitFor(() => {
      expect(storageService.get).toHaveBeenCalledWith('ss_error_log');
    });

    // We wait a bit to ensure async operations resolve/reject
    await new Promise((resolve) => {
      setTimeout(resolve, 10);
    });

    expect(storageService.set).not.toHaveBeenCalled();
  });

  it('swallows storageService.set error silently', async () => {
    vi.mocked(storageService.get).mockResolvedValueOnce(null);
    vi.mocked(storageService.set).mockRejectedValueOnce(new Error('Storage set failure'));

    render(
      <ErrorBoundary>
        <ThrowError message="Error 2" />
      </ErrorBoundary>
    );

    await waitFor(() => {
      expect(storageService.get).toHaveBeenCalledWith('ss_error_log');
    });

    await waitFor(() => {
      expect(storageService.set).toHaveBeenCalled();
    });
  });
});