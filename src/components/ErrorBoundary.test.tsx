import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { ErrorBoundary } from './ErrorBoundary';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { storageService } from '../services/storageService';

// Mock the storage service module
vi.mock('../services/storageService', () => {
  return {
    storageService: {
      get: vi.fn(),
      set: vi.fn(),
    }
  };
});

const ThrowError = () => {
  throw new Error('Test Error');
};

describe('ErrorBoundary', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Suppress React's error boundary logging to keep test output clean
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.clearAllMocks();
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('should catch errors and display fallback UI', () => {
    render(
      <ErrorBoundary fallback={<div data-testid="fallback">Custom Fallback</div>}>
        <ThrowError />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('fallback')).toBeInTheDocument();
  });

  it('should not bubble up exception when storageService.get fails', async () => {
    // Mock storageService.get to throw an error
    vi.mocked(storageService.get).mockRejectedValueOnce(new Error('Storage get failure'));

    expect(() => {
      render(
        <ErrorBoundary>
          <ThrowError />
        </ErrorBoundary>
      );
    }).not.toThrow();

    // Give some time for async logError to run
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(storageService.get).toHaveBeenCalledWith('ss_error_log');
    expect(storageService.set).not.toHaveBeenCalled();
  });

  it('should not bubble up exception when storageService.set fails', async () => {
    // Mock storageService.get to succeed, but set to throw
    vi.mocked(storageService.get).mockResolvedValueOnce('[]');
    vi.mocked(storageService.set).mockRejectedValueOnce(new Error('Storage set failure'));

    expect(() => {
      render(
        <ErrorBoundary>
          <ThrowError />
        </ErrorBoundary>
      );
    }).not.toThrow();

    // Give some time for async logError to run
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(storageService.get).toHaveBeenCalledWith('ss_error_log');
    expect(storageService.set).toHaveBeenCalled();
  });
});
