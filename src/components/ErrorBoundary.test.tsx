// @vitest-environment jsdom
import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import { expect, test, vi, describe, beforeEach, afterEach } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

// Mock storageService
const mockStorageGet = vi.fn();
const mockStorageSet = vi.fn();

vi.mock('../services/storageService', () => ({
  storageService: {
    get: mockStorageGet,
    set: mockStorageSet,
  }
}));

const FaultingComponent = () => {
  throw new Error('Test error');
};

describe('ErrorBoundary', () => {
  let consoleErrorSpy: any;

  beforeEach(() => {
    // Suppress console.error in tests
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    vi.clearAllMocks();
    cleanup();
  });

  test('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Test Child</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('Test Child')).toBeDefined();
  });

  test('catches error and logs it using storageService', async () => {
    mockStorageGet.mockResolvedValueOnce(JSON.stringify([{ time: 'old', context: 'ErrorBoundary', message: 'old error' }]));

    render(
      <ErrorBoundary>
        <FaultingComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeDefined();

    // Wait for the async logError to complete
    await vi.waitFor(() => {
      expect(mockStorageGet).toHaveBeenCalledWith('ss_error_log');
    });

    await vi.waitFor(() => {
      expect(mockStorageSet).toHaveBeenCalledTimes(1);
    });

    const setCallArgs = mockStorageSet.mock.calls[0];
    expect(setCallArgs[0]).toBe('ss_error_log');

    const savedLogs = JSON.parse(setCallArgs[1]);
    expect(savedLogs).toHaveLength(2);
    expect(savedLogs[0]).toEqual({ time: 'old', context: 'ErrorBoundary', message: 'old error' });
    expect(savedLogs[1].context).toBe('ErrorBoundary');
    expect(savedLogs[1].message).toBe('Test error');
    expect(savedLogs[1].time).toBeDefined();
  });

  test('catches error and falls back to empty array if storage get fails', async () => {
    mockStorageGet.mockResolvedValueOnce(null);

    render(
      <ErrorBoundary>
        <FaultingComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeDefined();

    await vi.waitFor(() => {
      expect(mockStorageSet).toHaveBeenCalledTimes(1);
    });

    const setCallArgs = mockStorageSet.mock.calls[0];
    const savedLogs = JSON.parse(setCallArgs[1]);
    expect(savedLogs).toHaveLength(1);
    expect(savedLogs[0].context).toBe('ErrorBoundary');
    expect(savedLogs[0].message).toBe('Test error');
  });

  test('catches error and silently handles storage set failure', async () => {
    mockStorageGet.mockResolvedValueOnce('[]');
    mockStorageSet.mockRejectedValueOnce(new Error('Storage failure'));

    render(
      <ErrorBoundary>
        <FaultingComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeDefined();

    await vi.waitFor(() => {
      expect(mockStorageSet).toHaveBeenCalledTimes(1);
    });

    // The component shouldn't crash despite the storage set failure
  });
});
