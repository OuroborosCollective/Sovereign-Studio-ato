import { describe, expect, it, vi } from 'vitest';
import { detectLanguage, fetchFileContent, isBinaryPath, isPreviewable, MAX_PREVIEW_BYTES } from './fileContentBrowserRuntime';

const response = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

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
  it('blocks without a workspace job', async () => {
    const result = await fetchFileContent({ jobId: '', backendBase: '', filePath: 'src/a.ts' });
    expect(result.status).toBe('blocked');
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
