import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildAreRepositoryState,
  evaluateAreInference,
  normalizeAreInferenceInput,
  quarantineAreResponse,
  repairMissingKnowledgeEmbeddings,
} from './areInferenceApi';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ARE inference adapter', () => {
  it('normalizes capabilities and repository files deterministically', () => {
    const normalized = normalizeAreInferenceInput({
      prompt: '  build adapter  ',
      onlineAvailable: true,
      activeCapabilities: ['zeta', 'alpha', 'alpha'],
      repository: {
        owner: ' owner ',
        repo: ' repo ',
        branch: ' main ',
        repositoryHash: 'ABC',
        changedFiles: [
          { path: 'z.ts', sha256: 'B' },
          { path: 'a.ts', sha256: 'A' },
        ],
      },
      limit: 99,
    });

    expect(normalized.prompt).toBe('build adapter');
    expect(normalized.activeCapabilities).toEqual(['alpha', 'zeta']);
    expect(normalized.repository.changedFiles.map((file) => file.path)).toEqual(['a.ts', 'z.ts']);
    expect(normalized.repository.repositoryHash).toBe('abc');
    expect(normalized.limit).toBe(8);
  });

  it('builds a stable repository state from a runtime snapshot', () => {
    const state = buildAreRepositoryState({
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
      branch: 'main',
      repositoryHash: 'scope-hash',
      filePaths: ['src/z.ts', 'src/a.ts'],
    });

    expect(state.changedFiles).toEqual([
      { path: 'src/a.ts', sha256: '' },
      { path: 'src/z.ts', sha256: '' },
    ]);
  });

  it('returns an honest blocked result from HTTP 409', async () => {
    const payload = {
      ok: false,
      schemaVersion: 1,
      stateHash: 'a'.repeat(64),
      state: {
        schemaVersion: 1,
        promptSha256: 'b'.repeat(64),
        repository: buildAreRepositoryState({}),
        knowledgeRevision: 'c'.repeat(64),
        experienceRevision: 'd'.repeat(64),
        embeddingModelHash: 'e'.repeat(64),
        activeCapabilities: [],
        onlineAvailable: false,
      },
      decision: 'blocked',
      adapter: 'none',
      confidence: 0,
      knowledgeConfidence: 0,
      experienceConfidence: 0,
      selectedKnowledgeIds: [],
      selectedPatternIds: [],
      knowledgeContext: '',
      experienceContext: '',
      knowledgeResults: [],
      experienceResults: [],
      reasons: ['offline_without_local_synthesis'],
      blockers: {},
      deterministic: true,
    } as const;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    })));

    const result = await evaluateAreInference({
      prompt: 'offline task',
      onlineAvailable: false,
    });

    expect(result.decision).toBe('blocked');
    expect(result.stateHash).toHaveLength(64);
  });

  it('uses only the allowlisted bounded knowledge repair action', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      action: 'recompute_missing_knowledge_embeddings',
      repaired: 2,
      remaining: 0,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await repairMissingKnowledgeEmbeddings(999);

    expect(result.repaired).toBe(2);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/inference/are/repair');
    expect(String(init.body)).toContain('recompute_missing_knowledge_embeddings');
    expect(String(init.body)).toContain('"limit":25');
  });

  it('stores successful online output only through the quarantine endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await quarantineAreResponse({
      prompt: 'task',
      response: 'result',
      stateHash: 'a'.repeat(64),
      adapter: 'online-accelerator',
      modelId: 'provider/model',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/inference/are/quarantine');
    expect(init.method).toBe('POST');
    expect(String(init.body)).toContain('online-accelerator');
  });
});
