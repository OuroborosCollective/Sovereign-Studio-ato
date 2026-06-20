// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import { publishRuntimeFeedback } from './appPublishRuntime';

describe('runtime feedback bridge', () => {
  it('sends coach state', () => {
    const listener = vi.fn();
    window.addEventListener('sovereign:runtime-coach-state', listener);

    publishRuntimeFeedback({
      allowed: false,
      status: 'idle',
      reason: 'Health idle prevents guarded output.',
      recommendations: ['Open Health.'],
      blockedReason: 'Health idle prevents guarded output.',
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
