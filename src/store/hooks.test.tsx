import React from 'react';
import { Provider } from 'react-redux';
import { act, renderHook } from '@testing-library/react';
import { configureStore } from '@reduxjs/toolkit';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  appReferenceEqual,
  appShallowEqual,
  useAppBooleanSelector,
  useAppDispatch,
  useAppNumberSelector,
  useAppSelector,
  useAppSelectorWithEquality,
  useAppShallowSelector,
  useAppStringSelector,
  useRequiredAppSelector,
  useRequiredAppShallowSelector,
} from './hooks';

interface CanvasState {
  objects: string[];
  selectedIds: string[];
  viewbox: {
    zoom: number;
    panX: number;
    panY: number;
  };
  isDragging: boolean;
}

interface BillingState {
  isSubscribed: boolean;
}

interface OuroborosState {
  isAuthSequenceActive: boolean;
  activeAREPayload: unknown;
  errorState: string | null;
  isRootInitialized: boolean;
  telemetry: unknown;
  resonance: unknown;
  guardReport: unknown;
  activePattern: string | null;
}

interface TestAction {
  type: string;
  payload?: unknown;
}

const initialCanvasState: CanvasState = {
  objects: [],
  selectedIds: [],
  viewbox: {
    zoom: 1,
    panX: 0,
    panY: 0,
  },
  isDragging: false,
};

const initialBillingState: BillingState = {
  isSubscribed: false,
};

const initialOuroborosState: OuroborosState = {
  isAuthSequenceActive: false,
  activeAREPayload: null,
  errorState: null,
  isRootInitialized: false,
  telemetry: null,
  resonance: null,
  guardReport: null,
  activePattern: null,
};

function canvasReducer(
  state: CanvasState = initialCanvasState,
  action: TestAction,
): CanvasState {
  switch (action.type) {
    case 'canvas/addObject':
      return {
        ...state,
        objects: [...state.objects, String(action.payload)],
      };

    case 'canvas/select':
      return {
        ...state,
        selectedIds: [...state.selectedIds, String(action.payload)],
      };

    case 'canvas/setZoom':
      return {
        ...state,
        viewbox: {
          ...state.viewbox,
          zoom: Number(action.payload),
        },
      };

    case 'canvas/setDragging':
      return {
        ...state,
        isDragging: Boolean(action.payload),
      };

    default:
      return state;
  }
}

function billingReducer(
  state: BillingState = initialBillingState,
  action: TestAction,
): BillingState {
  switch (action.type) {
    case 'billing/subscribe':
      return {
        ...state,
        isSubscribed: true,
      };

    case 'billing/unsubscribe':
      return {
        ...state,
        isSubscribed: false,
      };

    default:
      return state;
  }
}

function ouroborosReducer(
  state: OuroborosState = initialOuroborosState,
  action: TestAction,
): OuroborosState {
  switch (action.type) {
    case 'ouroboros/init':
      return {
        ...state,
        isRootInitialized: true,
      };

    case 'ouroboros/error':
      return {
        ...state,
        errorState: String(action.payload),
      };

    case 'ouroboros/clearError':
      return {
        ...state,
        errorState: null,
      };

    case 'ouroboros/pattern':
      return {
        ...state,
        activePattern: String(action.payload),
      };

    default:
      return state;
  }
}

function createTestStore() {
  return configureStore({
    reducer: {
      canvas: canvasReducer,
      billing: billingReducer,
      ouroboros: ouroborosReducer,
    },
  });
}

type TestStore = ReturnType<typeof createTestStore>;

function createWrapper(store: TestStore) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <Provider store={store}>{children}</Provider>;
  };
}

function renderWithStore<TResult>(
  hook: () => TResult,
  store: TestStore = createTestStore(),
) {
  return {
    store,
    ...renderHook(hook, {
      wrapper: createWrapper(store),
    }),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useAppDispatch', () => {
  it('returns the active store dispatch function', () => {
    const store = createTestStore();
    const { result } = renderWithStore(() => useAppDispatch(), store);

    expect(result.current).toBe(store.dispatch);
    expect(typeof result.current).toBe('function');
  });

  it('dispatches plain actions and returns the dispatched action', () => {
    const store = createTestStore();
    const { result } = renderWithStore(() => useAppDispatch(), store);

    const action = {
      type: 'canvas/addObject',
      payload: 'node-1',
    };

    expect(result.current(action)).toEqual(action);
    expect(store.getState().canvas.objects).toEqual(['node-1']);
  });

  it('keeps dispatch stable across rerenders', () => {
    const store = createTestStore();
    const { result, rerender } = renderWithStore(() => useAppDispatch(), store);

    const firstDispatch = result.current;

    rerender();

    expect(result.current).toBe(firstDispatch);
  });

  it('does not leak dispatched state into a fresh store', () => {
    const firstStore = createTestStore();
    const secondStore = createTestStore();

    firstStore.dispatch({
      type: 'canvas/addObject',
      payload: 'node-1',
    });

    expect(firstStore.getState().canvas.objects).toEqual(['node-1']);
    expect(secondStore.getState().canvas.objects).toEqual([]);
  });
});

describe('useAppSelector', () => {
  it('selects canvas state', () => {
    const { result } = renderWithStore(() => useAppSelector((state) => state.canvas));

    expect(result.current.objects).toEqual([]);
    expect(result.current.selectedIds).toEqual([]);
    expect(result.current.viewbox).toEqual({
      zoom: 1,
      panX: 0,
      panY: 0,
    });
    expect(result.current.isDragging).toBe(false);
  });

  it('selects billing state', () => {
    const { result } = renderWithStore(() => useAppSelector((state) => state.billing));

    expect(result.current.isSubscribed).toBe(false);
  });

  it('selects ouroboros state', () => {
    const { result } = renderWithStore(() => useAppSelector((state) => state.ouroboros));

    expect(result.current.isAuthSequenceActive).toBe(false);
    expect(result.current.isRootInitialized).toBe(false);
    expect(result.current.errorState).toBeNull();
    expect(result.current.guardReport).toBeNull();
    expect(result.current.activePattern).toBeNull();
  });

  it('updates selected values after dispatch', () => {
    const store = createTestStore();

    const { result } = renderWithStore(
      () => useAppSelector((state) => state.canvas.objects.length),
      store,
    );

    expect(result.current).toBe(0);

    act(() => {
      store.dispatch({
        type: 'canvas/addObject',
        payload: 'node-1',
      });
    });

    expect(result.current).toBe(1);
  });

  it('keeps unrelated selectors stable when unrelated state changes', () => {
    const store = createTestStore();

    const { result } = renderWithStore(
      () => useAppSelector((state) => state.canvas.objects.length),
      store,
    );

    expect(result.current).toBe(0);

    act(() => {
      store.dispatch({
        type: 'billing/subscribe',
      });
    });

    expect(result.current).toBe(0);
  });
});

describe('selector equality helpers', () => {
  it('exports reference and shallow equality helpers', () => {
    const shared = {
      value: 1,
    };

    expect(appReferenceEqual(shared, shared)).toBe(true);
    expect(appReferenceEqual({ value: 1 }, { value: 1 })).toBe(false);

    expect(appShallowEqual({ value: 1 }, { value: 1 })).toBe(true);
    expect(appShallowEqual({ value: 1 }, { value: 2 })).toBe(false);
  });

  it('supports custom equality through useAppSelectorWithEquality', () => {
    const store = createTestStore();

    const equality = vi.fn(
      (
        left: {
          zoom: number;
        },
        right: {
          zoom: number;
        },
      ) => left.zoom === right.zoom,
    );

    const { result } = renderWithStore(
      () =>
        useAppSelectorWithEquality(
          (state) => ({
            zoom: state.canvas.viewbox.zoom,
          }),
          equality,
        ),
      store,
    );

    const first = result.current;

    act(() => {
      store.dispatch({
        type: 'billing/subscribe',
      });
    });

    expect(result.current).toBe(first);
    expect(equality).toHaveBeenCalled();
  });

  it('updates custom equality selector when selected value changes', () => {
    const store = createTestStore();

    const { result } = renderWithStore(
      () =>
        useAppSelectorWithEquality(
          (state) => ({
            zoom: state.canvas.viewbox.zoom,
          }),
          (left, right) => left.zoom === right.zoom,
        ),
      store,
    );

    const first = result.current;

    act(() => {
      store.dispatch({
        type: 'canvas/setZoom',
        payload: 2,
      });
    });

    expect(result.current).not.toBe(first);
    expect(result.current.zoom).toBe(2);
  });

  it('supports shallow object selectors without replacing equal selected output', () => {
    const store = createTestStore();

    const { result } = renderWithStore(
      () =>
        useAppShallowSelector((state) => ({
          zoom: state.canvas.viewbox.zoom,
          panX: state.canvas.viewbox.panX,
          panY: state.canvas.viewbox.panY,
        })),
      store,
    );

    const first = result.current;

    act(() => {
      store.dispatch({
        type: 'billing/subscribe',
      });
    });

    expect(result.current).toBe(first);

    act(() => {
      store.dispatch({
        type: 'canvas/setZoom',
        payload: 2,
      });
    });

    expect(result.current).not.toBe(first);
    expect(result.current.zoom).toBe(2);
  });

  it('keeps shallow selector stable when parent slice object changes but selected fields stay equal', () => {
    const store = createTestStore();

    const { result } = renderWithStore(
      () =>
        useAppShallowSelector((state) => ({
          zoom: state.canvas.viewbox.zoom,
          panX: state.canvas.viewbox.panX,
          panY: state.canvas.viewbox.panY,
        })),
      store,
    );

    const first = result.current;

    act(() => {
      store.dispatch({
        type: 'canvas/addObject',
        payload: 'node-1',
      });
    });

    expect(result.current).toBe(first);
  });
});

describe('required selector hooks', () => {
  it('returns selected value when useRequiredAppSelector receives a value', () => {
    const { result } = renderWithStore(() =>
      useRequiredAppSelector((state) => state.canvas.viewbox, {
        name: 'canvas viewbox',
      }),
    );

    expect(result.current).toEqual({
      zoom: 1,
      panX: 0,
      panY: 0,
    });
  });

  it('throws a clear error when useRequiredAppSelector receives null', () => {
    expect(() =>
      renderWithStore(() =>
        useRequiredAppSelector((state) => state.ouroboros.errorState, {
          name: 'ouroboros error',
        }),
      ),
    ).toThrow('ouroboros error returned null or undefined');
  });

  it('throws a custom message when required selector options provide one', () => {
    expect(() =>
      renderWithStore(() =>
        useRequiredAppSelector(() => undefined, {
          message: 'Required runtime selection is missing.',
        }),
      ),
    ).toThrow('Required runtime selection is missing.');
  });

  it('supports required shallow selector for present object selections', () => {
    const { result } = renderWithStore(() =>
      useRequiredAppShallowSelector((state) => state.canvas.viewbox, {
        name: 'canvas viewbox',
      }),
    );

    expect(result.current).toEqual({
      zoom: 1,
      panX: 0,
      panY: 0,
    });
  });

  it('throws through required shallow selector for missing object selections', () => {
    expect(() =>
      renderWithStore(() =>
        useRequiredAppShallowSelector(() => null, {
          name: 'missing shallow selection',
        }),
      ),
    ).toThrow('missing shallow selection returned null or undefined');
  });

  it('returns required nullable-backed value once the store provides it', () => {
    const store = createTestStore();

    act(() => {
      store.dispatch({
        type: 'ouroboros/error',
        payload: 'runtime guard failed',
      });
    });

    const { result } = renderWithStore(
      () =>
        useRequiredAppSelector((state) => state.ouroboros.errorState, {
          name: 'ouroboros error',
        }),
      store,
    );

    expect(result.current).toBe('runtime guard failed');
  });
});

describe('primitive selector convenience hooks', () => {
  it('selects boolean values', () => {
    const { result } = renderWithStore(() =>
      useAppBooleanSelector((state) => state.billing.isSubscribed),
    );

    expect(result.current).toBe(false);
  });

  it('selects number values', () => {
    const { result } = renderWithStore(() =>
      useAppNumberSelector((state) => state.canvas.objects.length),
    );

    expect(result.current).toBe(0);
  });

  it('selects string values safely from nullable app state', () => {
    const { result } = renderWithStore(() =>
      useAppStringSelector((state) => state.ouroboros.errorState ?? ''),
    );

    expect(result.current).toBe('');
  });

  it('updates primitive selector values after store changes', () => {
    const store = createTestStore();

    const { result: subscribed } = renderWithStore(
      () => useAppBooleanSelector((state) => state.billing.isSubscribed),
      store,
    );

    const { result: objectCount } = renderWithStore(
      () => useAppNumberSelector((state) => state.canvas.objects.length),
      store,
    );

    const { result: errorText } = renderWithStore(
      () => useAppStringSelector((state) => state.ouroboros.errorState ?? ''),
      store,
    );

    expect(subscribed.current).toBe(false);
    expect(objectCount.current).toBe(0);
    expect(errorText.current).toBe('');

    act(() => {
      store.dispatch({
        type: 'billing/subscribe',
      });

      store.dispatch({
        type: 'canvas/addObject',
        payload: 'node-1',
      });

      store.dispatch({
        type: 'ouroboros/error',
        payload: 'runtime guard failed',
      });
    });

    expect(subscribed.current).toBe(true);
    expect(objectCount.current).toBe(1);
    expect(errorText.current).toBe('runtime guard failed');
  });
});

describe('typed hooks integration', () => {
  it('works with primitive selector patterns', () => {
    const { result: objectsResult } = renderWithStore(() =>
      useAppSelector((state) => state.canvas.objects.length),
    );

    const { result: billingResult } = renderWithStore(() =>
      useAppSelector((state) => state.billing.isSubscribed),
    );

    expect(objectsResult.current).toBe(0);
    expect(billingResult.current).toBe(false);
  });

  it('checks multiple values through separate stable selectors', () => {
    const store = createTestStore();

    const { result: objectCount } = renderWithStore(
      () => useAppSelector((state) => state.canvas.objects.length),
      store,
    );

    const { result: selectedCount } = renderWithStore(
      () => useAppSelector((state) => state.canvas.selectedIds.length),
      store,
    );

    const { result: subscribed } = renderWithStore(
      () => useAppSelector((state) => state.billing.isSubscribed),
      store,
    );

    const { result: rootInitialized } = renderWithStore(
      () => useAppSelector((state) => state.ouroboros.isRootInitialized),
      store,
    );

    expect(objectCount.current).toBe(0);
    expect(selectedCount.current).toBe(0);
    expect(subscribed.current).toBe(false);
    expect(rootInitialized.current).toBe(false);

    act(() => {
      store.dispatch({
        type: 'canvas/addObject',
        payload: 'node-1',
      });

      store.dispatch({
        type: 'canvas/select',
        payload: 'node-1',
      });

      store.dispatch({
        type: 'billing/subscribe',
      });

      store.dispatch({
        type: 'ouroboros/init',
      });
    });

    expect(objectCount.current).toBe(1);
    expect(selectedCount.current).toBe(1);
    expect(subscribed.current).toBe(true);
    expect(rootInitialized.current).toBe(true);
  });

  it('keeps independent hook renders connected to the same store coherently', () => {
    const store = createTestStore();

    const { result: dispatchResult } = renderWithStore(() => useAppDispatch(), store);

    const { result: zoomResult } = renderWithStore(
      () => useAppNumberSelector((state) => state.canvas.viewbox.zoom),
      store,
    );

    const { result: draggingResult } = renderWithStore(
      () => useAppBooleanSelector((state) => state.canvas.isDragging),
      store,
    );

    expect(zoomResult.current).toBe(1);
    expect(draggingResult.current).toBe(false);

    act(() => {
      dispatchResult.current({
        type: 'canvas/setZoom',
        payload: 3,
      });

      dispatchResult.current({
        type: 'canvas/setDragging',
        payload: true,
      });
    });

    expect(zoomResult.current).toBe(3);
    expect(draggingResult.current).toBe(true);
  });
});
