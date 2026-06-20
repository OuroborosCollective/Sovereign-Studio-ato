import { describe, expect, it } from 'vitest';
import {
  assertCanPublishPackage,
  canPublishPackage,
  evaluateCanPublishPackage,
  formatPublishGateMessage,
} from './appPublishRuntime';
import type { SovereignImplementationPackage } from './sovereignRuntime';
import type { RepoFile } from '../../github/types';
import type { SovereignHealthReport } from './sovereignHealth';
import type { SovereignHealthRuntimeGate } from './sovereignFunctionalGuards';

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

function createHealth(status: SovereignHealthReport['status'], recommendations: string[] = []): SovereignHealthReport {
  return {
    status,
    criticalRisks: status === 'red' ? 1 : 0,
    totalIssues: status === 'green' ? 0 : 1,
    repairsLogged: 0,
    branchDelta: 0,
    summary: `Health ${status}`,
    recommendations,
  };
}

function createRepoFiles(): RepoFile[] {
  return [{ path: 'README.md', type: 'blob' }];
}

function context(status: SovereignHealthReport['status'], recommendations: string[] = []) {
  return {
    repoFiles: createRepoFiles(),
    healthReport: createHealth(status, recommendations),
  };
}

describe('appPublishRuntime', () => {
  describe('assertCanPublishPackage', () => {
    it('passes when health is green', () => {
      expect(() => assertCanPublishPackage(createPackage(), context('green'))).not.toThrow();
    });

    it('passes when health is warning', () => {
      expect(() => assertCanPublishPackage(createPackage(), context('warning'))).not.toThrow();
    });

    it('throws with actionable feedback when health is red', () => {
      expect(() => assertCanPublishPackage(createPackage(), context('red', ['Open Health.', 'Fix blocked dependency.']))).toThrow(
        'Next: Open Health. | Fix blocked dependency.',
      );
    });

    it('throws when health is idle', () => {
      expect(() => assertCanPublishPackage(createPackage(), context('idle'))).toThrow('Health idle');
    });
  });

  describe('canPublishPackage', () => {
    it('returns structured allowed result when health is green', () => {
      const result = canPublishPackage(createPackage(), context('green'));
      expect(result.allowed).toBe(true);
      expect(result.status).toBe('green');
      expect(result.reason).toContain('Health green');
      expect(result.blockedReason).toBeUndefined();
    });

    it('returns structured blocked result with recommendations when health is red', () => {
      const result = canPublishPackage(createPackage(), context('red', ['Open Telemetry.', 'Resolve dependency.', 'Retry.', 'Ignored.']));
      expect(result.allowed).toBe(false);
      expect(result.status).toBe('red');
      expect(result.recommendations).toEqual(['Open Telemetry.', 'Resolve dependency.', 'Retry.']);
      expect(result.blockedReason).toContain('Open Telemetry. | Resolve dependency. | Retry.');
    });
  });

  describe('evaluateCanPublishPackage', () => {
    it('keeps package input side effect free while using health gate result', () => {
      const pkg = createPackage();
      const result = evaluateCanPublishPackage(pkg, context('warning', ['Review warning.']));
      expect(result.allowed).toBe(true);
      expect(result.status).toBe('warning');
      expect(pkg.files).toHaveLength(1);
    });
  });

  describe('formatPublishGateMessage', () => {
    it('adds compact recommendations to gate reason', () => {
      const gate: SovereignHealthRuntimeGate = {
        allowed: false,
        status: 'red',
        reason: 'Health red prevents guarded output: Health red',
        warnings: ['First.', 'Second.', 'Third.', 'Fourth.'],
      };
      expect(formatPublishGateMessage(gate)).toBe('Health red prevents guarded output: Health red Next: First. | Second. | Third.');
    });
  });
});
