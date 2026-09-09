import { describe, expect, it } from 'vitest';
import { runtimeObservation } from '../../../tests/e2e/helpers/live-runtime-observation';
const observe = (payload: unknown) => runtimeObservation('/api/user/agent/swarm/run', 'POST', 503, payload)!;

describe('tool failures are distinguished from absent tool calls', () => {
  it('retains actual per-role execution counters without copying arbitrary role keys', () => {
    const observed = observe({ repositoryTools: { callsByRole: { free_single_agent: 3 }, mutationsByRole: { free_single_agent: 0 }, consecutiveFailuresByRole: { free_single_agent: 3 }, openCircuits: ['free_single_agent'], writeConfirmed: true } });
    expect(observed.toolDiagnostics).toMatchObject({ callCount: 3, mutationCount: 0, consecutiveFailureCount: 3, circuitOpen: true, writeConfirmed: true });
  });
  it.each([undefined, null, '3', true, -1, 0.5, Infinity, NaN])('keeps malformed or missing counters unknown: %s', value => {
    const observed = observe({ repositoryTools: { callsByRole: { free_single_agent: value } } });
    expect(observed.toolDiagnostics.callCount).toBeNull();
  });
  it('does not manufacture a closed circuit from a missing field', () => {
    expect(observe({}).toolDiagnostics.circuitOpen).toBeNull();
  });
  it('keeps model-quoted failure hints explicitly non-authoritative', () => {
    const result = observe({ result: { assistant_text: 'installed MCP revision differs from the backend source revision' } });
    expect(result.nonAuthoritativeModelHints).toEqual({ source: 'model-output-not-runtime-proof', failureFamilies: ['MCP_RUNTIME_REVISION_MISMATCH'] });
    expect(result.failureFamily).toBeNull();
    expect(result.repositoryExecution.gatePassed).toBeNull();
  });
  it('never exports raw model text, event bodies or arbitrary secret-shaped values', () => {
    const secret = 'svk_' + 'synthetic-unit-only'.repeat(4);
    const result = observe({ result: { assistant_text: secret }, events: [{ message: secret }], repositoryTools: { callsByRole: { [secret]: 4 }, openCircuits: [secret] } });
    expect(JSON.stringify(result)).not.toContain(secret);
    expect(result.toolDiagnostics.jobEventCount).toBe(1);
  });
});
