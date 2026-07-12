// global-test-setup.ts
// Stubs jsdom navigation methods so tests that trigger page reload/assign don't fail
const originalLocation = globalThis.window?.location;

if (typeof window !== 'undefined' && window?.location) {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, reload: () => undefined, assign: () => undefined },
  });
}

export {};
