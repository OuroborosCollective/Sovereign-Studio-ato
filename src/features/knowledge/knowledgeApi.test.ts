import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  importKnowledgeUrl,
  importProgrammingLanguageCatalog,
  KnowledgeApiError,
  PROGRAMMING_LANGUAGE_CATALOG_REVISION,
} from './knowledgeApi';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('knowledgeApi failure evidence', () => {
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
