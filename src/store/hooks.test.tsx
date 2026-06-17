import React from 'react';
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useAppDispatch, useAppSelector } from './hooks';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

const testStore = configureStore({
  reducer: {
    canvas: (state = {
      objects: [],
      selectedIds: [],
      viewbox: { zoom: 1, panX: 0, panY: 0 },
      isDragging: false,
    }) => state,
    billing: (state = { isSubscribed: false }) => state,
    ouroboros: (state = { active: false }) => state,
  },
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <Provider store={testStore}>{children}</Provider>
);

describe('useAppDispatch', () => {
  it('returns a dispatch function', () => {
    const { result } = renderHook(() => useAppDispatch(), { wrapper });
    expect(result.current).toBe(testStore.dispatch);
    expect(typeof result.current).toBe('function');
  });

  it('dispatches plain actions', () => {
    const { result } = renderHook(() => useAppDispatch(), { wrapper });
    const action = { type: 'TEST_ACTION', payload: 'test' };
    expect(result.current(action)).toEqual(action);
  });
});

describe('useAppSelector', () => {
  it('selects canvas state', () => {
    const { result } = renderHook(() => useAppSelector((state) => state.canvas), { wrapper });
    expect(result.current.objects).toEqual([]);
    expect(result.current.viewbox).toEqual({ zoom: 1, panX: 0, panY: 0 });
    expect(result.current.isDragging).toBe(false);
  });

  it('selects viewbox state', () => {
    const { result } = renderHook(() => useAppSelector((state) => state.canvas.viewbox), { wrapper });
    expect(result.current.zoom).toBe(1);
    expect(result.current.panX).toBe(0);
    expect(result.current.panY).toBe(0);
  });

  it('selects billing state', () => {
    const { result } = renderHook(() => useAppSelector((state) => state.billing), { wrapper });
    expect(result.current.isSubscribed).toBe(false);
  });

  it('selects ouroboros state', () => {
    const { result } = renderHook(() => useAppSelector((state) => state.ouroboros), { wrapper });
    expect(result.current.active).toBe(false);
  });
});

describe('Typed hooks integration', () => {
  it('works with primitive selector patterns', () => {
    const { result: objectsResult } = renderHook(
      () => useAppSelector((state) => state.canvas.objects.length),
      { wrapper },
    );
    expect(objectsResult.current).toBe(0);

    const { result: billingResult } = renderHook(
      () => useAppSelector((state) => state.billing.isSubscribed),
      { wrapper },
    );
    expect(billingResult.current).toBe(false);
  });

  it('checks multiple values through separate stable selectors', () => {
    const { result: objectCount } = renderHook(
      () => useAppSelector((state) => state.canvas.objects.length),
      { wrapper },
    );
    const { result: selectedCount } = renderHook(
      () => useAppSelector((state) => state.canvas.selectedIds.length),
      { wrapper },
    );
    const { result: subscribed } = renderHook(
      () => useAppSelector((state) => state.billing.isSubscribed),
      { wrapper },
    );

    expect(objectCount.current).toBe(0);
    expect(selectedCount.current).toBe(0);
    expect(subscribed.current).toBe(false);
  });
});
