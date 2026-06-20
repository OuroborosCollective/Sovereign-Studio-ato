import { describe, expect, it, vi } from 'vitest';
import { assertCanPublishPackage, canPublishPackage } from './appPublishRuntime';
import type { SovereignImplementationPackage } from './sovereignRuntime';
import type { RepoFile } from '../../github/types';
import type { SovereignHealthReport } from './sovereignHealth';

function createPackage(): SovereignImplementationPackage {
  return {
    architecture: {
      summary: 'test',
      repoKind: 'node',
      hasReadme: true,
      hasGithubWorkflows: true,
      hasTests: true,
      hasRuntimeValidation: true,
      suggestedTargets: [],
      riskNotes: [],
    },
    brain: {
      perception: { domain: 'repo', intent: 'docs', architecture: 'node', confidence: 0.8 },
      analysis: { severity: 'medium', issues: [], rootCause: 'test', systemicRisk: 'test' },
      plan: { strategy: 'test', phases: [], estimatedComplexity: 'medium' },
      execution: { patches: [], integrationNotes: 'test', testStrategy: 'test' },
      learning: { patterns: [], rules: [], architectureUpgrade: 'test' },
    },
    files: [{ path: 'README.md', content: '# Test', reason: 'test' }],
    suggestions: [],
    providerRoutes: [],
    requestedWork: 'readme-docs',
  };
}

function createHealth(status: SovereignHealthReport['status']): SovereignHealthReport {
  return {
    status,
    criticalRisks: status === 'red' ? 1 : 0,
    totalIssues: status === 'green' ? 0 : 1,
    repairsLogged: 0,
    branchDelta: 0,
    summary: `Health ${status}`,
    recommendations: [],
  };
}

function createRepoFiles(): RepoFile[] {
  return [{ path: 'README.md', type: 'blob' }];
}

describe('appPublishRuntime', () => {
  describe('assertCanPublishPackage', () => {
    it('passes when health is green', () => {
      expect(() => assertCanPublishPackage(createPackage(), {
        repoFiles: createRepoFiles(),
        healthReport: createHealth('green'),
      })).not.toThrow();
    });

    it('passes when health is warning', () => {
      expect(() => assertCanPublishPackage(createPackage(), {
        repoFiles: createRepoFiles(),
        healthReport: createHealth('warning'),
      })).not.toThrow();
    });

    it('throws when health is red', () => {
      expect(() => assertCanPublishPackage(createPackage(), {
        repoFiles: createRepoFiles(),
        healthReport: createHealth('red'),
      })).toThrow('Health red');
    });

    it('throws when health is idle', () => {
      expect(() => assertCanPublishPackage(createPackage(), {
        repoFiles: createRepoFiles(),
        healthReport: createHealth('idle'),
      })).toThrow('Health idle');
    });
  });

  describe('canPublishPackage', () => {
    it('returns allowed:true when health is green', () => {
      const result = canPublishPackage(createPackage(), {
        repoFiles: createRepoFiles(),
        healthReport: createHealth('green'),
      });
      expect(result.allowed).toBe(true);
      expect(result.blockedReason).toBeUndefined();
    });

    it('returns allowed:false with reason when health is red', () => {
      const result = canPublishPackage(createPackage(), {
        repoFiles: createRepoFiles(),
        healthReport: createHealth('red'),
      });
      expect(result.allowed).toBe(false);
      expect(result.blockedReason).toContain('Health red');
    });
  });
});
