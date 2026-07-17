/**
 * useLlmAdapters Tests
 */

import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useLlmAdapters } from './useLlmAdapters';

describe('useLlmAdapters', () => {
  it('should return adapters array', () => {
    const { result } = renderHook(() => useLlmAdapters());
    
    expect(result.current.adapters).toBeDefined();
    expect(Array.isArray(result.current.adapters)).toBe(true);
  });

  it('should return enabled adapters', () => {
    const { result } = renderHook(() => useLlmAdapters());
    
    expect(result.current.enabledAdapters).toBeDefined();
    expect(Array.isArray(result.current.enabledAdapters)).toBe(true);
  });

  it('should return count of adapters', () => {
    const { result } = renderHook(() => useLlmAdapters());
    
    expect(typeof result.current.count).toBe('number');
    expect(result.current.count).toBeGreaterThanOrEqual(0);
  });

  it('should indicate if adapter is enabled', () => {
    const { result } = renderHook(() => useLlmAdapters());
    
    expect(typeof result.current.hasEnabledAdapter).toBe('boolean');
  });

  it('should expose only the backend route and local analysis fallback', () => {
    const { result } = renderHook(() => useLlmAdapters());

    expect(result.current.adapters.map((adapter) => adapter.id)).toEqual([
      'optional-user-keys',
      'local-safe',
    ]);
  });
});
