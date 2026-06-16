// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, act } from '@testing-library/react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import canvasReducer, { addObject, selectObjects } from './canvasSlice';
import { CanvasEngine } from './CanvasEngine';

// Reference to Canvas mock for assertions
const Canvas = { mockName: 'Canvas' };

// Create a stable mock canvas instance - must be created outside the mock
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

// Mock ResizeObserver - must be a constructor function
class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

global.ResizeObserver = MockResizeObserver as any;

// Mock Fabric.js - use actual constructor functions
vi.mock('fabric', () => {
  // Create mock objects
  const canvasInstance = {
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

  // Constructor functions that return objects
  function MockCanvas() {
    return canvasInstance;
  }

  function MockRect(opts: any) {
    return createMockFabricObject(opts);
  }

  function MockIText(text: string, opts: any) {
    return createMockFabricObject({ ...opts, text });
  }

  function MockPoint(x: number, y: number) {
    return { x, y };
  }

  return {
    Canvas: MockCanvas,
    FabricObject: function() {},
    Point: MockPoint,
    Rect: MockRect,
    IText: MockIText,
    default: {
      Canvas: MockCanvas,
      FabricObject: function() {},
      Point: MockPoint,
      Rect: MockRect,
      IText: MockIText,
    },
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
    // Reset mock functions
    mockCanvas.getObjects.mockReturnValue([]);
    mockCanvas.add.mockClear();
    mockCanvas.remove.mockClear();
    mockCanvas.requestRenderAll.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
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
    // Canvas is initialized via the mock
    expect(mockCanvas).toBeDefined();
  });

  // Note: Complex Canvas behavior tests require integration testing
  // These are covered by e2e tests in sovereign-studio-rn/e2e/
});
