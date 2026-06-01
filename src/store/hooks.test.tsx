import React from 'react';
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useAppDispatch, useAppSelector } from './hooks';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

// Create a minimal test store with just the shape we need
const testStore = configureStore({
  reducer: {
    canvas: (state = { 
      objects: [], 
      selectedIds: [], 
      viewbox: { zoom: 1, panX: 0, panY: 0 },
      isDragging: false 
    }) => state,
    billing: (state = { isSubscribed: false }) => state,
    ouroboros: (state = { active: false }) => state,
  },
});

// Wrapper for renderHook with Redux Provider
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <Provider store={testStore}>{children}</Provider>
);

describe('useAppDispatch', () => {
  it('should return a dispatch function', () => {
    const { result } = renderHook(() => useAppDispatch(), { wrapper });
    
    expect(result.current).toBe(testStore.dispatch);
    expect(typeof result.current).toBe('function');
  });

  it('should dispatch actions correctly', () => {
    const { result } = renderHook(() => useAppDispatch(), { wrapper });
    
    // Dispatch a simple action
    const action = { type: 'TEST_ACTION', payload: 'test' };
    const dispatchResult = result.current(action);
    
    // Thunk middleware returns the action itself for plain actions
    expect(dispatchResult).toEqual(action);
  });
});

describe('useAppSelector', () => {
  it('should select canvas state from the store', () => {
    const { result } = renderHook(() => useAppSelector((state) => state.canvas), { wrapper });
    
    expect(result.current).toBeDefined();
    expect(result.current).toHaveProperty('objects');
    expect(result.current).toHaveProperty('viewbox');
    expect(result.current).toHaveProperty('isDragging');
  });

  it('should select viewbox state correctly', () => {
    const { result } = renderHook(() => useAppSelector((state) => state.canvas.viewbox), { wrapper });
    
    expect(result.current).toBeDefined();
    expect(result.current).toHaveProperty('zoom');
    expect(result.current).toHaveProperty('panX');
    expect(result.current).toHaveProperty('panY');
  });

  it('should select billing state', () => {
    const { result } = renderHook(() => useAppSelector((state) => state.billing), { wrapper });
    
    expect(result.current).toBeDefined();
    expect(result.current).toHaveProperty('isSubscribed');
  });

  it('should select ouroboros state', () => {
    const { result } = renderHook(() => useAppSelector((state) => state.ouroboros), { wrapper });
    
    expect(result.current).toBeDefined();
    expect(result.current).toHaveProperty('active');
  });
});

describe('Typed hooks integration', () => {
  it('should work together for common patterns', () => {
    // Test selecting canvas objects
    const { result: objectsResult } = renderHook(
      () => useAppSelector((state) => state.canvas.objects),
      { wrapper }
    );
    expect(Array.isArray(objectsResult.current)).toBe(true);

    // Test selecting billing status
    const { result: billingResult } = renderHook(
      () => useAppSelector((state) => state.billing.isSubscribed),
      { wrapper }
    );
    expect(typeof billingResult.current).toBe('boolean');
  });

  it('should handle complex selectors', () => {
    const { result } = renderHook(
      () => useAppSelector((state) => ({
        objectCount: state.canvas.objects.length,
        selectedCount: state.canvas.selectedIds.length,
        isSubscribed: state.billing.isSubscribed,
      })),
      { wrapper }
    );
    
    expect(result.current).toHaveProperty('objectCount');
    expect(result.current).toHaveProperty('selectedCount');
    expect(result.current).toHaveProperty('isSubscribed');
    expect(typeof result.current.objectCount).toBe('number');
    expect(typeof result.current.selectedCount).toBe('number');
    expect(typeof result.current.isSubscribed).toBe('boolean');
  });
});
