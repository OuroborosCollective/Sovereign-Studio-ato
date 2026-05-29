// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, act } from '@testing-library/react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import canvasReducer, { addObject, selectObjects } from './canvasSlice';
import { CanvasEngine } from './CanvasEngine';
import { Canvas } from 'fabric';

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Create a stable mock object creator
const createMockFabricObject = (opts: any = {}) => ({
  set: vi.fn().mockReturnThis(),
  setCoords: vi.fn().mockReturnThis(),
  on: vi.fn(),
  off: vi.fn(),
  dispose: vi.fn(),
  left: 0,
  top: 0,
  width: opts.width || 0,
  height: opts.height || 0,
  scaleX: 1,
  scaleY: 1,
  ...opts,
});

// Create a stable mock canvas instance
const mockCanvas = {
  on: vi.fn(),
  off: vi.fn(),
  add: vi.fn(),
  remove: vi.fn(),
  moveObjectTo: vi.fn(),
  moveTo: vi.fn(),
  getObjects: vi.fn(() => []),
  item: vi.fn(),
  setDimensions: vi.fn(),
  dispose: vi.fn(),
  requestRenderAll: vi.fn(),
  getZoom: vi.fn(() => 1),
  zoomToPoint: vi.fn(),
  discardActiveObject: vi.fn(),
  setActiveObject: vi.fn(),
  getActiveObject: vi.fn(),
  setViewportTransform: vi.fn(),
  viewportTransform: [1, 0, 0, 1, 0, 0],
};

// Mock Fabric.js v7 named exports
vi.mock('fabric', () => {
  class MockFabricObject {
    static prototype: Record<string, unknown> = {};
  }

  return {
    Canvas: vi.fn(() => mockCanvas),
    FabricObject: MockFabricObject,
    Point: vi.fn((x: number, y: number) => ({ x, y })),
    Rect: vi.fn((opts: any) => createMockFabricObject(opts)),
    IText: vi.fn((text: string, opts: any) => createMockFabricObject({ ...opts, text })),
  };
});

describe('CanvasEngine', () => {
  let store: any;

  beforeEach(() => {
    store = configureStore({
      reducer: {
        canvas: canvasReducer,
      },
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    mockCanvas.getObjects.mockReturnValue([]);
  });

  it('renders without crashing', () => {
    const { container } = render(
      <Provider store={store}>
        <CanvasEngine />
      </Provider>,
    );
    expect(container.querySelector('canvas')).toBeDefined();
  });

  it('initializes fabric canvas on mount', () => {
    render(
      <Provider store={store}>
        <CanvasEngine />
      </Provider>,
    );
    expect(Canvas).toHaveBeenCalled();
  });

  it('adds objects to fabric canvas when redux state changes', async () => {
    const { rerender } = render(
      <Provider store={store}>
        <CanvasEngine />
      </Provider>,
    );

    const newObject = {
      id: 'test-1',
      type: 'rect',
      left: 10,
      top: 10,
      width: 100,
      height: 100,
      scaleX: 1,
      scaleY: 1,
      angle: 0,
      flipX: false,
      flipY: false,
      opacity: 1,
      visible: true,
      zIndex: 0,
      data: { color: '#ff0000' },
    };

    await act(async () => {
      store.dispatch(addObject(newObject));
    });

    rerender(
      <Provider store={store}>
        <CanvasEngine />
      </Provider>,
    );

    expect(mockCanvas.add).toHaveBeenCalled();
    expect(mockCanvas.requestRenderAll).toHaveBeenCalled();
  });

  it('sets active object based on primarySelectedId', async () => {
    const newObject = {
      id: 'test-select',
      type: 'rect',
      left: 10,
      top: 10,
      width: 100,
      height: 100,
      scaleX: 1,
      scaleY: 1,
      angle: 0,
      flipX: false,
      flipY: false,
      opacity: 1,
      visible: true,
      zIndex: 0,
      data: { color: '#00ff00' },
    };

    const fabricObj = createMockFabricObject({ id: 'test-select', left: 10, top: 10 });
    mockCanvas.getObjects.mockReturnValue([fabricObj as any]);
    mockCanvas.item.mockReturnValue(fabricObj);

    const { rerender } = render(
      <Provider store={store}>
        <CanvasEngine />
      </Provider>,
    );

    await act(async () => {
      store.dispatch(addObject(newObject));
    });

    await act(async () => {
      store.dispatch(selectObjects(['test-select']));
    });

    rerender(
      <Provider store={store}>
        <CanvasEngine />
      </Provider>,
    );

    expect(mockCanvas.setActiveObject).toHaveBeenCalledWith(fabricObj);
  });
});
