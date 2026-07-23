import { describe, expect, it, vi } from 'vitest';
import { detectFrameworkFromOutput, parseTestCounts, runTests } from './testRunnerRuntime';

const response = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('testRunnerRuntime', () => {
  it('detects pytest output', () => expect(detectFrameworkFromOutput('3 passed in 0.2s pytest')).toBe('pytest'));
  it('detects vitest output', () => expect(detectFrameworkFromOutput('Test Files  1 passed (1)\nTests  4 passed')).toBe('vitest'));
  it('detects jest output', () => expect(detectFrameworkFromOutput('PASS src/a.test.ts\nTests: 2 passed, 2 total')).toBe('jest'));
  it('detects go output', () => expect(detectFrameworkFromOutput('--- PASS: TestX\nok  \tpkg')).toBe('go_test'));
  it('detects cargo output', () => expect(detectFrameworkFromOutput('test result: ok. 2 passed')).toBe('cargo_test'));
  it('parses pytest counts', () => expect(parseTestCounts('7 passed, 2 failed, 1 error, 3 skipped')).toEqual({ passed: 7, failed: 2, errors: 1, skipped: 3 }));
  it('blocks without a job id', async () => expect((await runTests({ jobId: '', backendBase: '' })).status).toBe('blocked'));
  it('accepts real tool evidence even when evidence gate returns HTTP 400', async () => {
    const fetcher = vi.fn(async () => response(400, { tool: { status: 'done', stdout: '2 passed in 0.1s', exitCode: 0 } })) as unknown as typeof fetch;
    const result = await runTests({ jobId: 'job-1', backendBase: 'https://example.invalid', fetcher });
    expect(result.status).toBe('passed');
    expect(result.counts.passed).toBe(2);
  });
  it('reports a failed process exit', async () => {
    const fetcher = vi.fn(async () => response(400, { tool: { status: 'done', stdout: '1 failed, 2 passed', exitCode: 1 } })) as unknown as typeof fetch;
    const result = await runTests({ jobId: 'job-1', backendBase: 'https://example.invalid', fetcher });
    expect(result.status).toBe('failed');
    expect(result.hasRepairHint).toBe(true);
  });
  it('preserves backend blockers', async () => {
    const fetcher = vi.fn(async () => response(403, { tool: { status: 'blocked', blocker: 'workspace missing' } })) as unknown as typeof fetch;
    const result = await runTests({ jobId: 'job-1', backendBase: 'https://example.invalid', fetcher });
    expect(result.status).toBe('blocked');
    expect(result.blocker).toContain('workspace missing');
  });
  it('returns a network error without claiming tests ran', async () => {
    const fetcher = vi.fn(async () => { throw new Error('offline'); }) as unknown as typeof fetch;
    const result = await runTests({ jobId: 'job-1', backendBase: 'https://example.invalid', fetcher });
    expect(result.status).toBe('error');
    expect(result.counts.passed).toBe(0);
  });
});
