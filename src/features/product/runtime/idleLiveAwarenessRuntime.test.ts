import { describe, expect, it } from 'vitest';
import { isAgentRuntimeIdleForAwareness } from './idleLiveAwarenessRuntime';
import type { SovereignAgentJobSnapshot } from './sovereignAgentRuntime';

function job(status: SovereignAgentJobSnapshot['status']): SovereignAgentJobSnapshot {
  return { status, changedFiles: [], events: [] };
}

describe('idleLiveAwarenessRuntime', () => {
  it.each(['queued', 'provisioning', 'running', 'validating'] as const)(
    'pauses awareness while the latest agent job is %s',
    (status) => {
      expect(isAgentRuntimeIdleForAwareness([job(status)])).toBe(false);
    },
  );

  it.each(['idle', 'waiting-for-user', 'blocked', 'failed', 'completed', 'cleaned'] as const)(
    'allows read-only awareness while the latest agent job is %s',
    (status) => {
      expect(isAgentRuntimeIdleForAwareness([job(status)])).toBe(true);
    },
  );

  it('treats an empty job list as idle', () => {
    expect(isAgentRuntimeIdleForAwareness([])).toBe(true);
  });

  it('uses only the newest job as the idle authority signal', () => {
    expect(isAgentRuntimeIdleForAwareness([job('running'), job('completed')])).toBe(false);
    expect(isAgentRuntimeIdleForAwareness([job('completed'), job('running')])).toBe(true);
  });
});
