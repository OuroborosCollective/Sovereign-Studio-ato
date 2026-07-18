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
        repositoryRevision: 'ABC',
        evidenceComplete: true,
        files: [
          { path: 'z.ts', objectId: 'B' },
          { path: 'a.ts', objectId: 'A' },
        ],
      },
      limit: 99,
    });

    expect(normalized.prompt).toBe('build adapter');
    expect(normalized.activeCapabilities).toEqual(['alpha', 'zeta']);
    expect(normalized.repository.files.map((file) => file.path)).toEqual(['a.ts', 'z.ts']);
    expect(normalized.repository.repositoryRevision).toBe('abc');
    expect(normalized.repository.evidenceComplete).toBe(true);
    expect(normalized.limit).toBe(8);
  });

  it('builds a stable repository state from a runtime snapshot', () => {
    const state = buildAreRepositoryState({
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
      branch: 'main',
      repositoryRevision: 'tree-sha',
      files: [
        { path: 'src/z.ts', type: 'blob', sha: 'b'.repeat(40) },
        { path: 'src/a.ts', type: 'blob', sha: 'a'.repeat(40) },
      ],
    });

    expect(state.files).toEqual([
      { path: 'src/a.ts', objectId: 'a'.repeat(40) },
      { path: 'src/z.ts', objectId: 'b'.repeat(40) },
    ]);
    expect(state.repositoryRevision).toBe('tree-sha');
    expect(state.evidenceComplete).toBe(true);
  });

  it('marks repository evidence incomplete when Git object IDs are missing', () => {
    const state = buildAreRepositoryState({
      owner: 'owner',
      repo: 'repo',
      branch: 'main',
      repositoryRevision: 'tree-sha',
      files: [{ path: 'src/a.ts', type: 'blob' }],
    });
    expect(state.evidenceComplete).toBe(false);
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
        similarityScale: 1000000,
        activeCapabilities: [],
        onlineAvailable: false,
      },
      decision: 'blocked',
      adapter: 'none',
      confidence: 0,
      confidenceKappa: 0,
      knowledgeConfidence: 0,
      knowledgeConfidenceKappa: 0,
      experienceConfidence: 0,
      experienceConfidenceKappa: 0,
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
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      candidate: { id: 'candidate-1', status: 'pending', contentSha256: 'c'.repeat(64) },
      quarantined: true,
      duplicate: false,
      learningState: 'pending_evidence',
      promoted: false,
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await quarantineAreResponse({
      prompt: 'task',
      response: 'result',
      stateHash: 'a'.repeat(64),
      adapter: 'online-accelerator',
      modelId: 'provider/model',
    });

    expect(result.learningState).toBe('pending_evidence');
    expect(result.duplicate).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/inference/are/quarantine');
    expect(init.method).toBe('POST');
    expect(String(init.body)).toContain('online-accelerator');
  });
});
