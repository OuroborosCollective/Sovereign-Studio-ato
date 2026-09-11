import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { safeFailure, safeTestResult } from '../../../tests/e2e/helpers/live-safe-reporter';
import { runRequestObservation, runtimeObservation } from '../../../tests/e2e/helpers/live-runtime-observation';

describe('live reporter credential-recording regression', () => {
  it('never copies the credential-bearing step title or raw failure content into the safe result', () => {
    const credential = 'svk_' + 'synthetic-unit-secret'.repeat(3);
    const original = {
      status: 'failed' as const, duration: 20,
      errors: [{ message: `Fill "${credential}" failed`, stack: `Error ${credential}\n at five-draft-pr-paths.spec.ts:245:3` }],
      steps: [{ title: `Fill "${credential}"` }],
    };
    const projected = safeTestResult({ location: { file: 'five-draft-pr-paths.spec.ts', line: 458, column: 5 } }, original);
    expect(projected.status).toBe('failed');
    expect(projected.errors).toEqual([{ family: 'ASSERTION_OR_RUNTIME_FAILURE', line: 245 }]);
    expect(JSON.stringify(projected)).not.toContain(credential);
    expect(JSON.stringify(projected)).not.toContain('Fill');
    expect(projected).not.toHaveProperty('steps');
  });

  it.each([401, 403, 429, 500])('preserves the actual session failure family HTTP %i without a response body', status => {
    expect(safeFailure({ message: `LIVE_SESSION_HTTP_${status} response body must not be exported` })).toEqual({ family: `LIVE_SESSION_HTTP_${status}`, line: null });
  });

  it('preserves missing-evidence and setup-timeout failures instead of calling the suite green', () => {
    expect(safeFailure({ message: 'Expected exactly five GitHub-verified vNext Draft PR runs, received 0.' }).family).toBe('FIVE_DRAFT_PR_PROOF_INCOMPLETE');
    expect(safeFailure({ message: '"beforeAll" hook timeout of 30000ms exceeded.' }).family).toBe('SETUP_TIMEOUT');
  });

  it('publishes only fresh structured evidence, never the HTML report containing Fill arguments', () => {
    const workflow = readFileSync('.github/workflows/e2e-testing.yml', 'utf8').split('  live-five-path-draft-pr:')[1];
    expect(workflow).toContain('--reporter=./tests/e2e/helpers/live-safe-reporter.ts');
    expect(workflow).not.toContain('--reporter=list,html');
    expect(workflow).not.toContain('playwright-report/');
    expect(workflow).toContain('test-results/live-safe-reporter.json');
    expect(workflow).toContain('rm -f test-results/five-draft-pr-evidence.json test-results/live-safe-reporter.json');
    expect(workflow).toContain('if-no-files-found: error');
  });

  it('does not opt into an implicit second reporter or alter the Playwright result', () => {
    const source = readFileSync('tests/e2e/helpers/live-safe-reporter.ts', 'utf8');
    expect(source).toContain('printsToStdio() { return true; }');
    expect(source).toContain('onEnd(result: FullResult): void');
    expect(source).not.toContain('return { status:');
    expect(source).toContain('status: result.status');
  });
});


describe('live runtime observation projection', () => {
  const runId = 'run-' + 'a'.repeat(32);
  it('retains actual blocked run identity and next action without serializing arbitrary payload', () => {
    const result = runtimeObservation(`/api/user/agent/swarm/runs/${runId}`, 'GET', 200, {
      run: { runId, status: 'BLOCKED', jobId: 'job-1234', nextAction: 'REPAIR_ROUTE', reason: 'private material must not leave this object' },
      token: 'svk_' + 'a'.repeat(48),
    });
    expect(result).toMatchObject({ status: 'BLOCKED', requestedRunId: runId, returnedRunId: runId, identityMatches: true, nextAction: 'REPAIR_ROUTE' });
    expect(JSON.stringify(result)).not.toContain('svk_');
    expect(JSON.stringify(result)).not.toContain('private material');
  });
  it('records cross-run identity mismatch and HTTP failures rather than claiming success', () => {
    expect(runtimeObservation(`/api/user/agent/swarm/runs/${runId}`, 'GET', 200, { run: { runId: 'run-' + 'b'.repeat(32) } })?.identityMatches).toBe(false);
    expect(runtimeObservation('/api/user/agent/swarm/run', 'POST', 503, { blocker: 'NO_VERIFIED_EXECUTION_ROUTE_READY' })).toMatchObject({ httpStatus: 503, failureFamily: 'NO_VERIFIED_EXECUTION_ROUTE_READY' });
  });
  it('rejects secret-shaped metadata and never captures auth response bodies', () => {
    for (const secret of ['svk_', 'ghp_', 'github_pat_', 'sk-', 'hf_'].map(prefix => prefix + 'a'.repeat(32))) {
      const result = runtimeObservation('/api/user/agent/swarm/run', 'POST', 500, { status: secret, nextAction: secret, blocker: secret });
      expect(JSON.stringify(result)).not.toContain(secret);
    }
    expect(runtimeObservation('/api/auth/account-key', 'POST', 200, { key: 'not-for-reporter' })).toBeNull();
  });
  it('captures only allowlisted run-request contract fields and drops mission/credentials', () => {
    const secret = 'svk_' + 'synthetic-request-secret'.repeat(3);
    const result = runRequestObservation('/api/user/agent/swarm/run', 'POST', {
      mission: `do not persist ${secret}`,
      mode: 'free',
      agentMode: 'single',
      intentMode: 'repository_execution',
      repositoryUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repositoryBranch: 'main',
      githubAccessToken: secret,
    });
    expect(result).toEqual({
      route: 'swarm.start.request',
      mode: 'free',
      agentMode: 'single',
      intentMode: 'repository_execution',
      repositoryUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repositoryBranch: 'main',
    });
    expect(JSON.stringify(result)).not.toContain(secret);
  });
});
