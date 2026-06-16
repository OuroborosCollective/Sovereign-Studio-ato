import { describe, expect, it, vi } from 'vitest';
import {
  buildSovereignBranchName,
  publishPackageAsDraftPr,
  validatePublishableFiles,
} from './githubPackagePublisher';

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'ERROR',
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

describe('githubPackagePublisher', () => {
  it('rejects empty and forbidden publish files', () => {
    expect(() => validatePublishableFiles([])).toThrow('No files');
    expect(() => validatePublishableFiles([{ path: '.env', content: 'SECRET=1' }])).toThrow('forbidden');
    expect(() => validatePublishableFiles([{ path: 'README.md', content: '' }])).toThrow('empty');
    expect(() => validatePublishableFiles([{ path: '../README.md', content: 'x' }])).toThrow('Invalid');
  });

  it('builds deterministic branch names from package content', () => {
    const files = [{ path: 'README.md', content: '# Docs' }];
    expect(buildSovereignBranchName('sovereign/package', 'README + Update History', files)).toBe(
      buildSovereignBranchName('sovereign/package', 'README + Update History', files),
    );
    expect(buildSovereignBranchName('Bad Prefix!!', 'Title', files)).toMatch(/^bad-prefix\/[a-f0-9]{8}$/);
    expect(buildSovereignBranchName('Bad Prefix!!', 'Title', files, 'second')).not.toBe(
      buildSovereignBranchName('Bad Prefix!!', 'Title', files),
    );
  });

  it('publishes files through branch, tree, commit and draft PR calls', async () => {
    const calls: Array<{ url: string; method: string; body?: unknown }> = [];
    const fetcher = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
      calls.push({ url: String(url), method: init?.method ?? 'GET', body });

      const textUrl = String(url);
      if (textUrl.endsWith('/repos/OuroborosCollective/Sovereign-Studio-ato')) {
        return jsonResponse({ default_branch: 'main' });
      }
      if (textUrl.includes('/git/ref/heads/main')) {
        return jsonResponse({ object: { sha: 'base-sha' } });
      }
      if (textUrl.includes('/git/commits/base-sha')) {
        return jsonResponse({ tree: { sha: 'base-tree' } });
      }
      if (textUrl.endsWith('/git/refs')) {
        return jsonResponse({ ref: 'refs/heads/sovereign/package/test' });
      }
      if (textUrl.endsWith('/git/trees')) {
        return jsonResponse({ sha: 'new-tree' });
      }
      if (textUrl.endsWith('/git/commits')) {
        return jsonResponse({ sha: 'new-commit' });
      }
      if (textUrl.includes('/git/refs/heads/sovereign/package/')) {
        return jsonResponse({ object: { sha: 'new-commit' } });
      }
      if (textUrl.endsWith('/pulls')) {
        return jsonResponse({ number: 251, html_url: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/251' });
      }
      return jsonResponse({ message: 'not found' }, false, 404);
    });

    const result = await publishPackageAsDraftPr({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      token: 'token-for-test',
      title: 'Sovereign package',
      body: 'Generated package',
      files: [{ path: 'README.md', content: '# Docs' }],
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(result.pullRequestNumber).toBe(251);
    expect(calls.map((call) => call.method)).toEqual(['GET', 'GET', 'GET', 'POST', 'POST', 'POST', 'PATCH', 'POST']);
    expect(calls.at(-1)?.body).toMatchObject({ draft: true, base: 'main' });
  });

  it('falls forward to a numbered branch when the first branch already exists', async () => {
    let refCreateCalls = 0;
    const fetcher = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const textUrl = String(url);
      if (textUrl.endsWith('/repos/OuroborosCollective/Sovereign-Studio-ato')) return jsonResponse({ default_branch: 'main' });
      if (textUrl.includes('/git/ref/heads/main')) return jsonResponse({ object: { sha: 'base-sha' } });
      if (textUrl.includes('/git/commits/base-sha')) return jsonResponse({ tree: { sha: 'base-tree' } });
      if (textUrl.endsWith('/git/refs')) {
        refCreateCalls += 1;
        if (refCreateCalls === 1) return jsonResponse({ message: 'Reference already exists' }, false, 422);
        return jsonResponse({ ref: 'refs/heads/sovereign/package/collision-2' });
      }
      if (textUrl.endsWith('/git/trees')) return jsonResponse({ sha: 'new-tree' });
      if (textUrl.endsWith('/git/commits')) return jsonResponse({ sha: 'new-commit' });
      if (textUrl.includes('/git/refs/heads/sovereign/package/')) return jsonResponse({ object: { sha: 'new-commit' } });
      if (textUrl.endsWith('/pulls')) return jsonResponse({ number: 252, html_url: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/252' });
      return jsonResponse({ message: 'not found' }, false, 404);
    });

    const result = await publishPackageAsDraftPr({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      token: 'token-for-test',
      title: 'Sovereign package',
      body: 'Generated package',
      files: [{ path: 'README.md', content: '# Docs' }],
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(refCreateCalls).toBe(2);
    expect(result.branch).toMatch(/-2$/);
    expect(result.pullRequestNumber).toBe(252);
  });
});
