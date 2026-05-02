import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ErrorBoundary } from '../ErrorBoundary';
import * as storageModule from '../../services/storageService';

// Mock storageService dynamic import
vi.mock('../../services/storageService', () => {
  return {
    storageService: {
      get: vi.fn(),
      set: vi.fn(),
    }
  }
});

const FaultyComponent = () => {
  throw new Error('Test error');
  return null;
};

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div>Happy Path</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('Happy Path')).toBeInTheDocument();
  });

  it('renders default fallback when error occurs', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <FaultyComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    consoleSpy.mockRestore();
  });

  it('renders custom fallback when error occurs', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary fallback={<div>Custom Fallback</div>}>
        <FaultyComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText('Custom Fallback')).toBeInTheDocument();
    consoleSpy.mockRestore();
  });

  it('handles componentDidCatch and logs error to storage', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const mockedStorageService = (storageModule as any).storageService;
    mockedStorageService.get.mockResolvedValueOnce(JSON.stringify([
      { time: '2023-01-01T00:00:00.000Z', context: 'Other', message: 'Old error' }
    ]));

    // Mock Date globally rather than using FakeTimers, which might block the dynamic import promise
    const mockDate = new Date('2024-01-01T00:00:00.000Z');
    const originalDate = global.Date;

    class MockDate extends Date {
      constructor(...args: any[]) {
        if (args.length === 0) {
          super('2024-01-01T00:00:00.000Z');
        } else {
          super(...args as any);
        }
      }
      static now() {
        return mockDate.getTime();
      }
    }

    // @ts-ignore
    global.Date = MockDate;

    try {
      render(
        <ErrorBoundary fallback={<div>Custom Fallback</div>}>
          <FaultyComponent />
        </ErrorBoundary>
      );

      await waitFor(() => {
        expect(mockedStorageService.set).toHaveBeenCalled();
      });

      expect(mockedStorageService.set).toHaveBeenCalledWith(
        'ss_error_log',
        JSON.stringify([
          { time: '2023-01-01T00:00:00.000Z', context: 'Other', message: 'Old error' },
          { time: mockDate.toISOString(), context: 'ErrorBoundary', message: 'Test error' }
        ])
      );
    } finally {
      global.Date = originalDate;
      consoleSpy.mockRestore();
    }
  });
});
