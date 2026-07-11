import { beforeEach, describe, expect, it, vi } from 'vitest';

const emitSignal = vi.fn();
vi.mock('../../predictive/predictiveLayer', () => ({
  getDefaultPredictiveLayer: () => ({
    isEnabled: () => true,
    emitSignal,
  }),
}));

import { compareAreState, emitAreStateTransition } from './arePredictiveBridge';
import type { AreInferenceResult } from './areInferenceApi';

function result(overrides: Partial<AreInferenceResult['state']> = {}): AreInferenceResult {
  const state = {
    schemaVersion: 1,
    promptSha256: 'a'.repeat(64),
    repository: {
      owner: 'OuroborosCollective',
      repo: 'Sovereign-Studio-ato',
      branch: 'main',
      repositoryRevision: 'b'.repeat(64),
      files: [],
      evidenceComplete: true,
    },
    knowledgeRevision: 'c'.repeat(64),
    experienceRevision: 'd'.repeat(64),
    embeddingModelHash: 'e'.repeat(64),
    activeCapabilities: [],
    onlineAvailable: true,
    ...overrides,
  };
  return {
    ok: true,
    schemaVersion: 1,
    stateHash: `${state.promptSha256.slice(0, 32)}${state.repository.repositoryRevision.slice(0, 32)}`,
    state,
    decision: 'online_required',
    adapter: 'hybrid-memory-online',
    confidence: 0.9,
    knowledgeConfidence: 0.9,
    experienceConfidence: 0.9,
    selectedKnowledgeIds: [],
    selectedPatternIds: [],
    knowledgeContext: '',
    experienceContext: '',
    knowledgeResults: [],
    experienceResults: [],
    reasons: [],
    blockers: {},
    deterministic: true,
  };
}

beforeEach(() => {
  emitSignal.mockClear();
});

describe('ARE predictive bridge', () => {
  it('classifies the first observation without authorizing an action', () => {
    const current = result();
    const transition = compareAreState(null, current);

    expect(transition.changeKinds).toEqual(['initial']);
    expect(transition.changed).toBe(true);
    expect(transition.decision).toBe('online_required');
  });

  it('reports no change for the same deterministic state', () => {
    const current = result();
    const transition = compareAreState({ stateHash: current.stateHash, state: current.state }, current);

    expect(transition.changed).toBe(false);
    expect(transition.changeKinds).toEqual([]);
    expect(transition.magnitude).toBe(0);
  });

  it('classifies knowledge, repository and connectivity changes deterministically', () => {
    const previous = result();
    const current = result({
      knowledgeRevision: 'f'.repeat(64),
      repository: { ...previous.state.repository, repositoryRevision: '1'.repeat(64) },
      onlineAvailable: false,
    });
    const transition = compareAreState({ stateHash: previous.stateHash, state: previous.state }, current);

    expect(transition.changeKinds).toEqual(['repository', 'knowledge', 'connectivity']);
    expect(transition.magnitude).toBeCloseTo(3 / 7);
  });

  it('emits only advisory metadata into the existing predictive layer', () => {
    const current = result();
    emitAreStateTransition(null, current);

    expect(emitSignal).toHaveBeenCalledTimes(1);
    expect(emitSignal).toHaveBeenCalledWith(
      'are.inference.state',
      expect.any(Number),
      expect.objectContaining({
        stateHash: current.stateHash,
        deterministic: true,
        authority: 'advisory-only',
      }),
    );
  });
});
