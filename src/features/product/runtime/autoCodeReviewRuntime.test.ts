import { describe, expect, it, vi } from 'vitest';
import { findingsByFile, requestAutoCodeReview, reviewAllowsDraftPr, reviewBlockerMessage, severityIcon } from './autoCodeReviewRuntime';

const response = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('autoCodeReviewRuntime', () => {
  it('allows only a passed decision', () => expect(reviewAllowsDraftPr({ decision: 'passed', passed: true } as never)).toBe(true));
  it('does not allow a contradictory passed=false result', () => expect(reviewAllowsDraftPr({ decision: 'passed', passed: false } as never)).toBe(false));
  it('blocks high findings', () => expect(reviewAllowsDraftPr({ decision: 'blocked_high', passed: false } as never)).toBe(false));
  it('blocks unavailable review', () => expect(reviewAllowsDraftPr({ decision: 'blocked_unavailable', passed: false } as never)).toBe(false));
  it('formats high blocker text', () => expect(reviewBlockerMessage({ decision: 'blocked_high', highCount: 2, summary: 'fix' } as never)).toContain('2 HIGH'));
  it('groups findings by file', () => {
    const grouped = findingsByFile([
      { severity: 'LOW', category: 'style', file: 'a.ts', lineHint: '1', description: 'a' },
      { severity: 'MEDIUM', category: 'quality', file: 'a.ts', lineHint: '2', description: 'b' },
      { severity: 'LOW', category: 'style', file: 'b.ts', lineHint: '1', description: 'c' },
    ]);
    expect(grouped.get('a.ts')).toHaveLength(2);
    expect(grouped.get('b.ts')).toHaveLength(1);
  });
  it('maps severity icons', () => {
    expect(severityIcon('HIGH')).toBe('🔴');
    expect(severityIcon('MEDIUM')).toBe('🟡');
    expect(severityIcon('LOW')).toBe('🟢');
  });
  it('blocks missing job id before fetch', async () => {
    const fetcher = vi.fn() as unknown as typeof fetch;
    const result = await requestAutoCodeReview({ jobId: '', backendBase: '', fetcher });
    expect(result.decision).toBe('blocked_unavailable');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('parses passed FreeLLM evidence', async () => {
    const fetcher = vi.fn(async () => response(200, { decision: 'passed', passed: true, summary: 'ok', findings: [], highCount: 0, mediumCount: 0, lowCount: 0, modelUsed: 'free/model', resolvedTransport: 'freellm', routeId: 'f1', attemptedRouteCount: 1 })) as unknown as typeof fetch;
    const result = await requestAutoCodeReview({ jobId: 'j1', backendBase: 'https://example.invalid', fetcher });
    expect(result.passed).toBe(true);
    expect(result.resolvedTransport).toBe('freellm');
  });
  it('parses paid OpenRouter evidence', async () => {
    const fetcher = vi.fn(async () => response(200, { decision: 'passed', passed: true, summary: 'ok', findings: [], highCount: 0, mediumCount: 1, lowCount: 0, modelUsed: 'openai/model', resolvedTransport: 'openrouter', routeId: 'p1', attemptedRouteCount: 1 })) as unknown as typeof fetch;
    const result = await requestAutoCodeReview({ jobId: 'j1', backendBase: 'https://example.invalid', fetcher });
    expect(result.passed).toBe(true);
    expect(result.resolvedTransport).toBe('openrouter');
  });
  it('keeps a high finding blocked even on HTTP 200', async () => {
    const fetcher = vi.fn(async () => response(200, { decision: 'blocked_high', passed: false, summary: 'blocked', findings: [{ severity: 'HIGH', category: 'security', file: 'a.py', lineHint: '1', description: 'unsafe' }], highCount: 1 })) as unknown as typeof fetch;
    const result = await requestAutoCodeReview({ jobId: 'j1', backendBase: 'https://example.invalid', fetcher });
    expect(reviewAllowsDraftPr(result)).toBe(false);
    expect(result.findings[0].severity).toBe('HIGH');
  });
  it('turns an impossible HTTP failure/pass contradiction into unavailable', async () => {
    const fetcher = vi.fn(async () => response(503, { decision: 'passed', passed: true })) as unknown as typeof fetch;
    const result = await requestAutoCodeReview({ jobId: 'j1', backendBase: 'https://example.invalid', fetcher });
    expect(result.decision).toBe('blocked_unavailable');
  });
  it('returns unavailable on network failure', async () => {
    const fetcher = vi.fn(async () => { throw new Error('offline'); }) as unknown as typeof fetch;
    const result = await requestAutoCodeReview({ jobId: 'j1', backendBase: 'https://example.invalid', fetcher });
    expect(result.decision).toBe('blocked_unavailable');
    expect(result.error).toContain('offline');
  });
});
