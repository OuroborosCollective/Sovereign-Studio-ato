// @vitest-environment jsdom

import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const render = vi.fn();

  return {
    render,
    createRoot: vi.fn(() => ({ render })),
    posthogInit: vi.fn(),
    restoreCanvasStateMirror: vi.fn(async () => undefined),
    flushCanvasStateMirror: vi.fn(async () => undefined),
    warn: vi.fn(),
  };
});

vi.mock('react-dom/client', () => ({
  createRoot: mocks.createRoot,
}));

vi.mock('posthog-js', () => ({
  default: {
    init: mocks.posthogInit,
  },
}));

vi.mock('./App', () => ({
  default: () => React.createElement('div', { 'data-testid': 'mock-app' }, 'App'),
}));

vi.mock('./components/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock('./store', () => ({
  restoreCanvasStateMirror: mocks.restoreCanvasStateMirror,
  flushCanvasStateMirror: mocks.flushCanvasStateMirror,
}));

type TestWindow = Window & typeof globalThis & {
  __sovereignViewportRuntimeInstalled?: boolean;
  __sovereignMobileRuntimeInstalled?: boolean;
  __sovereignCodeWorkspacePersistenceInstalled?: boolean;
  requestIdleCallback?: unknown;
  cancelIdleCallback?: unknown;
  global?: unknown;
};

function resetWindowFlags(): void {
  const win = window as TestWindow;

  delete win.__sovereignViewportRuntimeInstalled;
  delete win.__sovereignMobileRuntimeInstalled;
  delete win.__sovereignCodeWorkspacePersistenceInstalled;
  delete win.requestIdleCallback;
  delete win.cancelIdleCallback;
  delete win.global;
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();

  document.head.innerHTML = '';
  document.body.innerHTML = '<div id="root"></div>';
  document.documentElement.className = '';
  resetWindowFlags();

  Object.defineProperty(window, 'innerWidth', { value: 390, configurable: true });
  Object.defineProperty(window, 'innerHeight', { value: 844, configurable: true });
  Object.defineProperty(window, 'devicePixelRatio', { value: 2, configurable: true });

  vi.spyOn(console, 'warn').mockImplementation(mocks.warn);
});

describe('mobile entrypoint runtime boot', () => {
  it('installs viewport and persistence then renders the React root', async () => {
    await import('./main');

    const win = window as TestWindow;

    expect(win.global).toBe(window);
    expect(typeof win.requestIdleCallback).toBe('function');
    expect(typeof win.cancelIdleCallback).toBe('function');
    expect(win.__sovereignViewportRuntimeInstalled).toBe(true);
    expect(win.__sovereignMobileRuntimeInstalled).toBeUndefined();
    expect(win.__sovereignCodeWorkspacePersistenceInstalled).toBe(true);

    expect(document.documentElement.classList.contains('device-phone')).toBe(true);
    expect(document.documentElement.classList.contains('is-portrait')).toBe(true);
    expect(document.documentElement.classList.contains('regular-height')).toBe(true);
    expect(document.getElementById('sovereign-mobile-runtime-style')).toBeDefined();

    expect(mocks.restoreCanvasStateMirror).toHaveBeenCalledWith({
      dispatch: true,
      clearInvalid: true,
    });
    expect(mocks.createRoot).toHaveBeenCalledWith(document.getElementById('root'));
    expect(mocks.render).toHaveBeenCalledOnce();
  });

  it('warns and skips React boot when root container is missing', async () => {
    document.body.innerHTML = '';

    await import('./main');

    expect(mocks.warn).toHaveBeenCalledWith('React root container #root not found.');
    expect(mocks.createRoot).not.toHaveBeenCalled();
  });
});
