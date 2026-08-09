import { describe, expect, it, vi } from 'vitest';
import {
  evaluateIdleAwarenessTransition,
  fetchIdleLiveAwarenessObservation,
  isStrictWorkflowGreen,
  normalizeIdleLiveAwarenessMode,
  parseIdleAwarenessPullRequestUrl,
  startIdleLiveAwareness,
  type IdleLiveAwarenessObservation,
} from './idleLiveAwareness';
import { buildLocalWorkflowWatchReport } from './workflowWatch';

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function observation(overrides: Partial<IdleLiveAwarenessObservation> = {}): IdleLiveAwarenessObservation {
  const workflow = buildLocalWorkflowWatchReport({
    commitSha: 'a'.repeat(40),
    checks: [{
      name: 'Revision Guardian',
      status: 'green',
      conclusion: 'success',
      source: 'check-run',
      summary: 'success',
    }],
    checkedAt: 1,
  });
  return {
    repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
    prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1326',
    prNumber: 1326,
    headSha: 'a'.repeat(40),
    checkedAt: 1,
    workflow,
    terminalGreen: true,
    fingerprint: 'fingerprint-a',
    ...overrides,
  };
}

describe('idleLiveAwareness', () => {
  it('defaults unknown modes to off', () => {
    expect(normalizeIdleLiveAwarenessMode('observe')).toBe('observe');
    expect(normalizeIdleLiveAwarenessMode('observe-notify')).toBe('observe-notify');
    expect(normalizeIdleLiveAwarenessMode('always')).toBe('off');
  });

  it('parses only canonical GitHub pull request URLs', () => {
    expect(parseIdleAwarenessPullRequestUrl('https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1326')).toEqual({
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
      prNumber: 1326,
    });
    expect(parseIdleAwarenessPullRequestUrl('https://example.com/pull/1326')).toBeNull();
  });

  it('does not call skipped or neutral checks strictly green', () => {
    const skipped = buildLocalWorkflowWatchReport({
      checks: [{ name: 'optional', status: 'green', conclusion: 'skipped', source: 'check-run', summary: 'skipped' }],
      checkedAt: 1,
    });
    const success = buildLocalWorkflowWatchReport({
      checks: [{ name: 'required', status: 'green', conclusion: 'success', source: 'check-run', summary: 'success' }],
      checkedAt: 1,
    });
    expect(isStrictWorkflowGreen(skipped)).toBe(false);
    expect(isStrictWorkflowGreen(success)).toBe(true);
  });

  it('resets green evidence when the PR head changes', () => {
    const previous = observation();
    const current = observation({ headSha: 'b'.repeat(40), fingerprint: 'fingerprint-b', terminalGreen: false });
    expect(evaluateIdleAwarenessTransition(previous, current)).toEqual({
      changed: true,
      shouldNotify: false,
      reason: 'head-changed',
    });
  });

  it('notifies on the first transition to terminal green', () => {
    const previous = observation({ terminalGreen: false, fingerprint: 'pending' });
    const current = observation({ terminalGreen: true, fingerprint: 'green' });
    expect(evaluateIdleAwarenessTransition(previous, current)).toEqual({
      changed: true,
      shouldNotify: true,
      reason: 'became-green',
    });
  });

  it('reads the PR head then evaluates commit status and check runs without writes', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({ number: 1326, head: { sha: 'c'.repeat(40) } }))
      .mockResolvedValueOnce(response({ state: 'success', statuses: [] }))
      .mockResolvedValueOnce(response({ check_runs: [
        { name: 'Revision Guardian', status: 'completed', conclusion: 'success', output: { summary: 'ok' } },
        { name: 'Release Gate', status: 'completed', conclusion: 'success', output: { summary: 'ok' } },
      ] }));

    const result = await fetchIdleLiveAwarenessObservation({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1326',
    }, fetcher);

    expect(result.headSha).toBe('c'.repeat(40));
    expect(result.terminalGreen).toBe(true);
    expect(fetcher).toHaveBeenCalledTimes(3);
    for (const call of fetcher.mock.calls) {
      const init = call[1] as RequestInit | undefined;
      expect(init?.method ?? 'GET').toBe('GET');
    }
  });

  it('does not probe while off or while the app is not idle', async () => {
    const fetcher = vi.fn<typeof fetch>();
    const offController = startIdleLiveAwareness({
      mode: 'off',
      target: {
        repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
        prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1326',
      },
      isIdle: () => true,
      fetcher,
    });
    expect(await offController.probeNow()).toBeNull();

    const busyController = startIdleLiveAwareness({
      mode: 'observe',
      target: {
        repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
        prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/1326',
      },
      isIdle: () => false,
      fetcher,
      pollMs: 30_000,
    });
    expect(await busyController.probeNow()).toBeNull();
    busyController.stop();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
