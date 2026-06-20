// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import { publishRuntimeFeedback } from './appPublishRuntime';

describe('runtime feedback coach signal', () => {
  it('sends a coach event', () => {
    const listener = vi.fn();
    window.addEventListener('sovereign:runtime-coach-state', listener);

    publishRuntimeFeedback({
      allowed: false,
      status: 'idle',
      reason: 'needs review',
      recommendations: ['Open Health.'],
      blockedReason: 'needs review',
    }, 123);

    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toMatchObject({
      lamp: 'yellow',
      source: 'runtime',
      action: 'Open Health.',
      updatedAt: 123,
    });

    window.removeEventListener('sovereign:runtime-coach-state', listener);
  });
});
