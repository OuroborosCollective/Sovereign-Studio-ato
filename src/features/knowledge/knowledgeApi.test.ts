import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  deleteKnowledgeSource,
  getKnowledgeStats,
  importKnowledgeUrl,
  importProgrammingLanguageCatalog,
  KnowledgeApiError,
  PROGRAMMING_LANGUAGE_CATALOG_REVISION,
  uploadKnowledgeFile,
} from './knowledgeApi';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('knowledgeApi failure evidence', () => {
  it('reads knowledge statistics through the canonical authenticated endpoint', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      sources: 2,
      sourceChunks: 8,
      sourceBytes: 1024,
      uniqueBlocks: 6,
      embeddedBlocks: 5,
      textBytes: 900,
      embeddingModel: 'bounded-model',
      storage: 'postgres-pgvector',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const stats = await getKnowledgeStats();

    expect(fetchMock).toHaveBeenCalledWith(
      'https://sovereign-backend.arelorian.de/api/knowledge/stats',
      { credentials: 'include' },
    );
    expect(stats).toMatchObject({ sources: 2, embeddedBlocks: 5, storage: 'postgres-pgvector' });
  });

  it('imports one URL through the canonical JSON endpoint', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      duplicate: false,
      source: { id: 'source-1', title: 'Bound source', status: 'ready' },
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await importKnowledgeUrl('https://example.test/source', 'Bound source');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://sovereign-backend.arelorian.de/api/knowledge/sources/url',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: 'https://example.test/source', title: 'Bound source' }),
      }),
    );
    expect(result.duplicate).toBe(false);
  });

  it('binds upload ticket, object PUT and confirmation without skipping verification', async () => {
    const statuses: string[] = [];
    vi.stubGlobal('crypto', {
      subtle: {
        digest: vi.fn(async () => new Uint8Array(32).fill(1).buffer),
      },
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/knowledge/sources/upload-ticket')) {
        return new Response(JSON.stringify({
          objectId: 'object-1',
          uploadUrl: 'https://upload.example.test/object-1',
          headers: { 'X-Bound-Upload': 'yes' },
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url === 'https://upload.example.test/object-1') {
        expect(init).toMatchObject({
          method: 'PUT',
          headers: { 'X-Bound-Upload': 'yes' },
        });
        expect(init?.body).toBeInstanceOf(File);
        return new Response('', { status: 200 });
      }
      if (url.endsWith('/api/knowledge/sources/upload-confirm')) {
        return new Response(JSON.stringify({
          duplicate: false,
          source: { id: 'source-upload', title: 'notes.txt', status: 'processing' },
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ error: 'unexpected endpoint' }), { status: 500 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const file = new File(['bounded knowledge'], 'notes.txt', { type: 'text/plain' });

    const result = await uploadKnowledgeFile(file, status => statuses.push(status));

    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual([
      'https://sovereign-backend.arelorian.de/api/knowledge/sources/upload-ticket',
      'https://upload.example.test/object-1',
      'https://sovereign-backend.arelorian.de/api/knowledge/sources/upload-confirm',
    ]);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      filename: 'notes.txt',
      contentType: 'text/plain',
      sizeBytes: file.size,
      sha256: '01'.repeat(32),
    });
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual({ objectId: 'object-1' });
    expect(statuses).toEqual(['preparing', 'uploading', 'verifying', 'processing', 'completed']);
    expect(result.source.id).toBe('source-upload');
  });

  it('deletes only the encoded owned source path and waits for backend confirmation', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await deleteKnowledgeSource('source/with spaces');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://sovereign-backend.arelorian.de/api/knowledge/sources/source%2Fwith%20spaces',
      expect.objectContaining({ method: 'DELETE', credentials: 'include' }),
    );
  });

  it('imports the pinned programming-language catalog through its dedicated endpoint', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      ok: true,
      duplicate: false,
      catalogRevision: PROGRAMMING_LANGUAGE_CATALOG_REVISION,
      source: {
        id: 'catalog-source',
        title: 'ProgrammiersprachenMD · kuratierter Sprachkatalog',
        sourceType: 'github',
        status: 'ready',
        chunkCount: 22,
      },
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await importProgrammingLanguageCatalog();

    expect(fetchMock).toHaveBeenCalledWith(
      'https://sovereign-backend.arelorian.de/api/knowledge/catalogs/programming-languages/import',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: '{}',
      }),
    );
    expect(result.catalogRevision).toBe(PROGRAMMING_LANGUAGE_CATALOG_REVISION);
    expect(result.source.title).toContain('ProgrammiersprachenMD');
  });

  it('preserves a structured GitHub credential blocker and upstream status', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ok: false,
      error: 'Der hinterlegte GitHub-Zugang wurde von GitHub abgelehnt.',
      blocker: 'github_credentials_rejected',
      githubHttpStatus: 403,
      correlationId: '3b4cd00e-506b-41ce-8d95-1d0f18a1416b',
      auditRecorded: true,
    }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    })));

    const error = await importKnowledgeUrl('https://github.com/OuroborosCollective/Sovereign-Studio-ato')
      .then(() => null, (reason: unknown) => reason);

    expect(error).toBeInstanceOf(KnowledgeApiError);
    expect(error).toMatchObject({
      responseStatus: 409,
      blocker: 'github_credentials_rejected',
      githubHttpStatus: 403,
      correlationId: '3b4cd00e-506b-41ce-8d95-1d0f18a1416b',
      auditRecorded: true,
    });
    expect((error as Error).message).toContain('serverseitige GitHub-Zugang');
    expect((error as Error).message).toContain('GitHub HTTP 403');
    expect((error as Error).message).toContain('Fehler-ID: 3b4cd00e-506b-41ce-8d95-1d0f18a1416b');
    expect((error as Error).message).toContain('Audit: gespeichert');
  });

  it('does not mislabel an unstructured backend 403 as a GitHub token failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 403 })));

    const error = await importKnowledgeUrl('https://github.com/OuroborosCollective/Sovereign-Studio-ato')
      .then(() => null, (reason: unknown) => reason);

    expect(error).toBeInstanceOf(KnowledgeApiError);
    expect(error).toMatchObject({ responseStatus: 403 });
    expect((error as Error).message).toContain('keinen GitHub-Ursachenblocker');
    expect((error as Error).message).toContain('deployed Backend-Revision');
    expect((error as Error).message).not.toContain('Token fehlt');
  });

  it('keeps rate-limit evidence separate from credential rejection', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ok: false,
      blocker: 'github_rate_limit_exhausted',
      githubHttpStatus: 403,
    }), {
      status: 429,
      headers: { 'Content-Type': 'application/json' },
    })));

    const error = await importKnowledgeUrl('https://github.com/OuroborosCollective/Sovereign-Studio-ato')
      .then(() => null, (reason: unknown) => reason);

    expect(error).toBeInstanceOf(KnowledgeApiError);
    expect(error).toMatchObject({
      responseStatus: 429,
      blocker: 'github_rate_limit_exhausted',
      githubHttpStatus: 403,
    });
    expect((error as Error).message).toContain('API-Limit');
    expect((error as Error).message).not.toContain('Zugang wurde abgelehnt');
  });
});
