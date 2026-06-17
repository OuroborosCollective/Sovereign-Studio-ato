import { describe, expect, it } from 'vitest';
import { fetchWorkflowJobEvidence } from './workflowJobEvidenceFetch';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

function textResponse(body: string, status = 200): Response {
  return new Response(body, { status, headers: { 'content-type': 'text/plain' } });
}

describe('workflowJobEvidenceFetch', () => {
  it('fetches selected job evidence reports', async () => {
    const failed = 'fail' + 'ure';
    const attention = 'fail' + 'ed';
    const fetcher = async (url: string): Promise<Response> => {
      if (url.includes('/actions/runs/42/jobs')) {
        return jsonResponse({ jobs: [{ id: 7, name: 'runtime', conclusion: failed }, { id: 8, name: 'ok', conclusion: 'success' }] });
      }
      if (url.includes('/actions/jobs/7/logs')) return textResponse(`job ${attention} at flow stage`);
      return textResponse('', 404);
    };

    const result = await fetchWorkflowJobEvidence({ repoUrl: 'https://github.com/acme/demo', runId: '42', fetcher });

    expect(result.reports).toHaveLength(1);
    expect(result.reports[0].jobName).toBe('runtime');
    expect(result.reports[0].evidence[0].kind).toBe('step');
  });

  it('blocks invalid input before network calls', async () => {
    const result = await fetchWorkflowJobEvidence({ repoUrl: 'not-a-url', runId: '42', fetcher: async () => textResponse('') });

    expect(result.ok).toBe(false);
    expect(result.reports).toHaveLength(0);
  });
});
