import { describe, expect, it, vi } from 'vitest';
import { detectLanguage, fetchFileContent, isBinaryPath, isPreviewable, MAX_PREVIEW_BYTES } from './fileContentBrowserRuntime';

const response = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const repositoryFetcher = (
  revision: string,
  fileBody: Record<string, unknown>,
  readStatus = 200,
) => vi.fn(async (url, init) => {
  const endpoint = String(url);
  const payload = JSON.parse(String(init?.body));
  expect(endpoint).toBe('https://example.invalid/api/user/agent/repository/read-file');
  expect(payload).toMatchObject({
    scope: 'signed-repository-file-read-scope',
    owner: 'OuroborosCollective',
    repo: 'Sovereign-Studio-ato',
    ref: revision,
  });
  return response(readStatus, {
    scopeVerified: true,
    repositoryRevision: revision,
    revision,
    ...fileBody,
  });
}) as unknown as typeof fetch;

describe('fileContentBrowserRuntime', () => {
  it('detects TypeScript', () => expect(detectLanguage('src/a.tsx')).toBe('typescript'));
  it('detects Python', () => expect(detectLanguage('backend/a.py')).toBe('python'));
  it('detects markdown', () => expect(detectLanguage('README.md')).toBe('markdown'));
  it('rejects binary paths', () => {
    expect(isBinaryPath('image.png')).toBe(true);
    expect(isPreviewable('image.png')).toBe(false);
  });
  it('allows text paths', () => expect(isPreviewable('src/a.ts')).toBe(true));
  it('blocks path traversal before fetch', async () => {
    const fetcher = vi.fn() as unknown as typeof fetch;
    const result = await fetchFileContent({ jobId: 'j', backendBase: '', filePath: '../secret', fetcher });
    expect(result.status).toBe('blocked');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('blocks without a workspace job or repository identity', async () => {
    const result = await fetchFileContent({ jobId: '', backendBase: '', filePath: 'src/a.ts' });
    expect(result.status).toBe('blocked');
  });
  it('pins repository fallback reads to the loaded immutable snapshot after the branch advances', async () => {
    const loadedSnapshotRevision = 'a'.repeat(40);
    const currentBranchHead = 'b'.repeat(40);
    const blobSha = 'c'.repeat(40);
    expect(currentBranchHead).not.toBe(loadedSnapshotRevision);
    const fetcher = repositoryFetcher(loadedSnapshotRevision, {
      content: 'License text at snapshot A',
      bytes: 26,
      sha: blobSha,
    });
    const result = await fetchFileContent({
      jobId: '',
      backendBase: 'https://example.invalid',
      filePath: 'LICENSE',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: loadedSnapshotRevision,
      repositoryReadScope: 'signed-repository-file-read-scope',
      fetcher,
    });
    expect(result.status).toBe('loaded');
    expect(result.content).toBe('License text at snapshot A');
    expect(result.sha).toBe(blobSha);
  });
  it('uses the immutable repository fallback after a selected workspace is typed unusable', async () => {
    const loadedSnapshotRevision = 'a'.repeat(40);
    const blobSha = 'd'.repeat(40);
    const fetcher = repositoryFetcher(loadedSnapshotRevision, {
      content: 'README at immutable snapshot',
      bytes: 28,
      sha: blobSha,
    });
    const result = await fetchFileContent({
      jobId: 'cleaned-workspace-job',
      workspaceUsable: false,
      backendBase: 'https://example.invalid',
      filePath: 'README.md',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: loadedSnapshotRevision,
      repositoryReadScope: 'signed-repository-file-read-scope',
      fetcher,
    });
    expect(result.status).toBe('loaded');
    expect(result.sha).toBe(blobSha);
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it('blocks mutable branch names for repository fallback previews', async () => {
    const fetcher = vi.fn() as unknown as typeof fetch;
    const result = await fetchFileContent({
      jobId: '',
      backendBase: 'https://example.invalid',
      filePath: 'LICENSE',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: 'main',
      fetcher,
    });
    expect(result.status).toBe('blocked');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('honors backend truncation even when original bytes remain below the frontend limit', async () => {
    const content = 'x'.repeat(60_000);
    const revision = 'a'.repeat(40);
    const fetcher = repositoryFetcher(revision, {
      content,
      bytes: 80_000,
      sha: 'd'.repeat(40),
      truncated: true,
    });
    const result = await fetchFileContent({
      jobId: '',
      backendBase: 'https://example.invalid',
      filePath: 'docs/large.md',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: revision,
      repositoryReadScope: 'signed-repository-file-read-scope',
      fetcher,
    });
    expect(result.status).toBe('loaded');
    expect(result.truncated).toBe(true);
    expect(result.content).toContain('[... content truncated at preview boundary ...]');
  });
  it('rejects repository content without an immutable blob identity', async () => {
    const revision = 'a'.repeat(40);
    const fetcher = repositoryFetcher(revision, {
      content: 'unbound content',
      bytes: 15,
      sha: '',
    });
    const result = await fetchFileContent({
      jobId: '',
      backendBase: 'https://example.invalid',
      filePath: 'README.md',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: revision,
      repositoryReadScope: 'signed-repository-file-read-scope',
      fetcher,
    });
    expect(result.status).toBe('error');
    expect(result.error).toContain('immutable blob identity');
  });
  it('rejects repository evidence when the readback revision drifts from the signed snapshot', async () => {
    const revision = 'a'.repeat(40);
    const fetcher = repositoryFetcher(revision, {
      content: 'newer branch content',
      bytes: 20,
      sha: 'e'.repeat(40),
      repositoryRevision: 'b'.repeat(40),
    });
    const result = await fetchFileContent({
      jobId: '',
      backendBase: 'https://example.invalid',
      filePath: 'README.md',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: revision,
      repositoryReadScope: 'signed-repository-file-read-scope',
      fetcher,
    });
    expect(result.status).toBe('error');
    expect(result.error).toContain('revision-drifted');
  });
  it('derives a narrow read scope from exact revision validation before fallback read', async () => {
    const revision = 'a'.repeat(40);
    const fetcher = vi.fn(async (url, init) => {
      const endpoint = String(url);
      const payload = JSON.parse(String(init?.body));
      if (endpoint.endsWith('/github-access/scope')) {
        expect(payload).toMatchObject({
          repository: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
          branch: revision,
          expectedBaseSha: revision,
          purpose: 'github-access-validate',
        });
        return response(200, {
          ok: true,
          scope: 'parent-validation-scope',
          baseSha: revision,
          purpose: 'github-access-validate',
        });
      }
      if (endpoint.endsWith('/github-access/validate')) {
        expect(payload).toEqual({ scope: 'parent-validation-scope' });
        return response(200, {
          ok: false,
          canWrite: false,
          repositoryReadScope: 'derived-read-scope',
          repositoryRevision: revision,
        });
      }
      expect(endpoint).toBe('https://example.invalid/api/user/agent/repository/read-file');
      expect(payload.scope).toBe('derived-read-scope');
      return response(200, {
        ok: true,
        scopeVerified: true,
        repositoryRevision: revision,
        revision,
        content: 'public immutable content',
        bytes: 24,
        sha: 'b'.repeat(40),
      });
    }) as unknown as typeof fetch;
    const result = await fetchFileContent({
      jobId: '',
      backendBase: 'https://example.invalid',
      filePath: 'README.md',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: revision,
      fetcher,
    });
    expect(result.status).toBe('loaded');
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
  it('fails closed when exact revision validation cannot issue a parent scope', async () => {
    const revision = 'a'.repeat(40);
    const fetcher = vi.fn(async () => response(422, {
      ok: false,
      error: 'revision scope unavailable',
    })) as unknown as typeof fetch;
    const result = await fetchFileContent({
      jobId: '',
      backendBase: 'https://example.invalid',
      filePath: 'README.md',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: revision,
      fetcher,
    });
    expect(result.status).toBe('blocked');
    expect(result.error).toContain('revision scope unavailable');
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it('refreshes one expired cached read scope exactly once', async () => {
    const revision = 'a'.repeat(40);
    let readCalls = 0;
    const fetcher = vi.fn(async (url, init) => {
      const endpoint = String(url);
      const payload = JSON.parse(String(init?.body));
      if (endpoint.endsWith('/repository/read-file')) {
        readCalls += 1;
        if (readCalls === 1) {
          expect(payload.scope).toBe('expired-read-scope');
          return response(422, { code: 'repository_file_scope_unverified' });
        }
        expect(payload.scope).toBe('refreshed-read-scope');
        return response(200, {
          scopeVerified: true,
          repositoryRevision: revision,
          revision,
          content: 'refreshed content',
          bytes: 17,
          sha: 'c'.repeat(40),
        });
      }
      if (endpoint.endsWith('/github-access/scope')) {
        return response(200, {
          ok: true,
          scope: 'parent-validation-scope',
          baseSha: revision,
          purpose: 'github-access-validate',
        });
      }
      return response(200, {
        repositoryReadScope: 'refreshed-read-scope',
        repositoryRevision: revision,
      });
    }) as unknown as typeof fetch;
    const result = await fetchFileContent({
      jobId: '',
      backendBase: 'https://example.invalid',
      filePath: 'README.md',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: revision,
      repositoryReadScope: 'expired-read-scope',
      fetcher,
    });
    expect(result.status).toBe('loaded');
    expect(readCalls).toBe(2);
    expect(fetcher).toHaveBeenCalledTimes(4);
  });
  it('forwards a manual PAT only request-locally through scope validation and private read', async () => {
    const revision = 'a'.repeat(40);
    const token = `ghp_${'s'.repeat(40)}`;
    const requestBodies: string[] = [];
    const fetcher = vi.fn(async (url, init) => {
      const endpoint = String(url);
      const bodyText = String(init?.body);
      requestBodies.push(bodyText);
      const payload = JSON.parse(bodyText);
      expect(payload.githubAccessToken).toBe(token);
      if (endpoint.endsWith('/github-access/scope')) {
        return response(200, {
          ok: true,
          scope: 'private-parent-scope',
          baseSha: revision,
          purpose: 'github-access-validate',
        });
      }
      if (endpoint.endsWith('/github-access/validate')) {
        return response(200, {
          ok: true,
          canWrite: true,
          repositoryReadScope: 'private-read-scope',
          repositoryRevision: revision,
        });
      }
      return response(200, {
        scopeVerified: true,
        repositoryRevision: revision,
        revision,
        content: 'private content',
        bytes: 15,
        sha: 'd'.repeat(40),
      });
    }) as unknown as typeof fetch;
    const result = await fetchFileContent({
      jobId: '',
      workspaceUsable: false,
      backendBase: 'https://example.invalid',
      filePath: 'README.md',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: revision,
      githubAccessToken: token,
      fetcher,
    });
    expect(result.status).toBe('loaded');
    expect(result.content).toBe('private content');
    expect(result.content).not.toContain(token);
    expect(requestBodies).toHaveLength(3);
  });
  it('maps a backend-detected binary file without accepting content', async () => {
    const revision = 'a'.repeat(40);
    const fetcher = repositoryFetcher(revision, {
      status: 'binary',
      error: 'unsupported UTF-8',
    }, 415);
    const result = await fetchFileContent({
      jobId: '',
      backendBase: 'https://example.invalid',
      filePath: 'assets/opaque.dat',
      repoOwner: 'OuroborosCollective',
      repoName: 'Sovereign-Studio-ato',
      repoRevision: revision,
      repositoryReadScope: 'signed-repository-file-read-scope',
      fetcher,
    });
    expect(result.status).toBe('binary');
    expect(result.content).toBe('');
  });
  it('returns a binary result without network access', async () => {
    const fetcher = vi.fn() as unknown as typeof fetch;
    const result = await fetchFileContent({ jobId: 'j', backendBase: '', filePath: 'asset.zip', fetcher });
    expect(result.status).toBe('binary');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('reads real workspace tool output', async () => {
    const fetcher = vi.fn(async () => response(200, { tool: { status: 'done', stdout: 'export const x = 1;', metadata: { bytes: 19, sha256: 'abc' } } })) as unknown as typeof fetch;
    const result = await fetchFileContent({ jobId: 'j', backendBase: 'https://example.invalid', filePath: 'src/a.ts', fetcher });
    expect(result.status).toBe('loaded');
    expect(result.content).toContain('export const');
    expect(result.sha).toBe('abc');
  });
  it('maps a missing file', async () => {
    const fetcher = vi.fn(async () => response(404, { tool: { status: 'error', error: 'File not found: a.ts' } })) as unknown as typeof fetch;
    const result = await fetchFileContent({ jobId: 'j', backendBase: 'https://example.invalid', filePath: 'a.ts', fetcher });
    expect(result.status).toBe('not_found');
  });
  it('preserves backend policy blockers', async () => {
    const fetcher = vi.fn(async () => response(403, { tool: { status: 'blocked', blocker: 'workspace boundary' } })) as unknown as typeof fetch;
    const result = await fetchFileContent({ jobId: 'j', backendBase: 'https://example.invalid', filePath: 'a.ts', fetcher });
    expect(result.status).toBe('blocked');
    expect(result.error).toContain('workspace boundary');
  });
  it('bounds requested preview bytes', async () => {
    const fetcher = vi.fn(async (_url, init) => {
      const payload = JSON.parse(String(init?.body));
      expect(payload.maxBytes).toBe(MAX_PREVIEW_BYTES);
      return response(200, { tool: { status: 'done', stdout: 'x', metadata: { bytes: 1 } } });
    }) as unknown as typeof fetch;
    await fetchFileContent({ jobId: 'j', backendBase: 'https://example.invalid', filePath: 'a.ts', maxBytes: MAX_PREVIEW_BYTES * 5, fetcher });
  });
  it('returns network errors without file content', async () => {
    const fetcher = vi.fn(async () => { throw new Error('offline'); }) as unknown as typeof fetch;
    const result = await fetchFileContent({ jobId: 'j', backendBase: 'https://example.invalid', filePath: 'a.ts', fetcher });
    expect(result.status).toBe('error');
    expect(result.content).toBe('');
  });
});
