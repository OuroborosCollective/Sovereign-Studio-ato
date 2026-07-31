import { describe, expect, it } from 'vitest';
import type { RepoFile } from '../../github/types';
import type {
  RepoInsightEngineOutput,
  RepoInsightSuggestion,
} from '../runtime/repoInsightEngine';
import {
  buildRepoEvidenceIndex,
  gateOutput,
  hasRepoEvidence,
} from './RepoInsightPanelBridge';

function suggestion(
  category: RepoInsightSuggestion['category'],
  affectedFiles: string[],
): RepoInsightSuggestion {
  return {
    id: `suggestion-${category}`,
    category,
    title: 'Gezielter Vorschlag',
    whyUseful: 'Der Vorschlag ist durch echte Repository-Pfade begründet.',
    affectedFiles,
    risk: 'niedrig',
    expectedBenefit: 'Weniger wiederholte Repository-Scans beim Rendern.',
    actionLabel: 'Prüfen',
    priority: 1,
  };
}

function output(featureSuggestion: RepoInsightSuggestion): RepoInsightEngineOutput {
  return {
    fixSuggestions: [],
    hardeningSuggestions: [],
    featureSuggestions: [featureSuggestion],
    recommendedMission: 'Erweitere die Repository-Analyse.',
    recommendedMissionConfidence: 0.9,
    confidence: 0.9,
    blockers: [],
    coachStatus: 'green',
    coachMessage: 'Repository analysiert.',
    analyzedFiles: 3,
    findings: [],
  };
}

describe('RepoInsightPanelBridge suggestion gating', () => {
  const repoFiles: RepoFile[] = [
    { path: 'src/features/product/components/RepoInsightPanelBridge.tsx', type: 'blob' },
    { path: 'src/features/product/runtime/repoInsightEngine.ts', type: 'blob' },
    { path: '.github/workflows/release-verification.yml', type: 'blob' },
  ];

  it('indexes exact paths and directory prefixes once for constant-time evidence checks', () => {
    const index = buildRepoEvidenceIndex(repoFiles);

    expect(hasRepoEvidence('src/features/product/components/RepoInsightPanelBridge.tsx', index)).toBe(true);
    expect(hasRepoEvidence('/src/features/product/components/', index)).toBe(true);
    expect(hasRepoEvidence('src/features/product', index)).toBe(true);
    expect(hasRepoEvidence('src/features/missing', index)).toBe(false);
  });

  it('uses indexed evidence while preserving the existing hard-blocker policy', () => {
    const gated = gateOutput(
      output(suggestion('feature', ['src/features/product/components/', 'missing/path.ts'])),
      repoFiles,
    );
    const allowedGate = (gated.featureSuggestions[0] as RepoInsightSuggestion & {
      gate?: { state: string; evidenceFiles: string[] };
    }).gate;

    expect(allowedGate).toEqual({
      state: 'allowed',
      reason: 'Vorschlag ist durch Repo-Struktur oder Runtime-Finding belegt.',
      nextAction: 'use_suggestion',
      evidenceFiles: ['src/features/product/components/'],
    });

    const blocked = gateOutput(
      {
        ...output(suggestion('feature', ['src/features/product/components/'])),
        blockers: [{ type: 'ci-failure', message: 'Release Gate ist rot.' }],
      },
      repoFiles,
    );
    const blockedGate = (blocked.featureSuggestions[0] as RepoInsightSuggestion & {
      gate?: { state: string; evidenceFiles: string[] };
    }).gate;

    expect(blockedGate?.state).toBe('blocked');
    expect(blockedGate?.evidenceFiles).toEqual(['src/features/product/components/']);
    expect(blocked.featureSuggestions[0].actionLabel).toBe('Gate prüfen');
  });
});
