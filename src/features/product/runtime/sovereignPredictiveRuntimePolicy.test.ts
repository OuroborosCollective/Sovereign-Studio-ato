import { describe, expect, it } from 'vitest';
import type { CapabilityDecision } from './sovereignCapabilityTypes';
import type { PredictiveActionDecision } from './sovereignPredictiveActionRuntime';
import {
  assertPredictiveRuntimePolicy,
  evaluatePredictiveRuntimePolicy,
} from './sovereignPredictiveRuntimePolicy';

const packageRequiredDecision: CapabilityDecision = {
  route: 'draft-pr-runtime',
  capability: 'draft_pr',
  allowed: false,
  reason: 'Draft PR Runtime blockiert: Patch-Paket/Diff muss zuerst erzeugt werden',
  blocker: 'package_required',
  nextAction: 'generate_patch_package',
};

const packagePrediction: PredictiveActionDecision = {
  action: 'generate_patch_package',
  signal: 'runtime_contract',
  confidence: 'high',
  reason: 'Draft PR benötigt zuerst ein Patch-Paket.',
  learnedFrom: 1,
  surfaces: ['router', 'menu', 'inspector', 'runtime'],
};

describe('sovereignPredictiveRuntimePolicy', () => {
  it('allows a package_required prediction that only suggests generate_patch_package', () => {
    const result = evaluatePredictiveRuntimePolicy({
      capabilityDecision: packageRequiredDecision,
      prediction: packagePrediction,
      runtime: {
        repoReady: true,
        githubAccessState: 'ready',
        githubWriteAllowed: true,
        hasPackage: false,
      },
    });

    expect(result.allowed).toBe(true);
    expect(result.violations).toEqual([]);
    expect(result.checkedPolicies).toContain('draft_pr_requires_patch_package');
  });

  it('blocks execution mode because predictive runtime may not execute', () => {
    const result = evaluatePredictiveRuntimePolicy({
      mode: 'execution',
      capabilityDecision: packageRequiredDecision,
      prediction: packagePrediction,
    });

    expect(result.allowed).toBe(false);
    expect(result.violations.map((violation) => violation.code)).toContain('no_autonomous_write');
  });

  it('blocks secret-like values in predictive payloads', () => {
    const result = evaluatePredictiveRuntimePolicy({
      capabilityDecision: packageRequiredDecision,
      prediction: {
        ...packagePrediction,
        reason: 'Use github_pat_1234567890SECRETSECRETSECRET in this flow.',
      },
    });

    expect(result.allowed).toBe(false);
    expect(result.violations.map((violation) => violation.code)).toContain('no_secret_learning');
  });

  it('blocks unknown actions', () => {
    const result = evaluatePredictiveRuntimePolicy({
      capabilityDecision: packageRequiredDecision,
      prediction: {
        ...packagePrediction,
        action: 'merge_main' as never,
      },
    });

    expect(result.allowed).toBe(false);
    expect(result.violations.map((violation) => violation.code)).toContain('unknown_action_blocks');
  });

  it('blocks unknown surfaces', () => {
    const result = evaluatePredictiveRuntimePolicy({
      capabilityDecision: packageRequiredDecision,
      prediction: {
        ...packagePrediction,
        surfaces: ['router', 'secret_dashboard' as never],
      },
    });

    expect(result.allowed).toBe(false);
    expect(result.violations.map((violation) => violation.code)).toContain('unknown_surface_blocks');
  });

  it('blocks package_required if prediction tries to skip patch package generation', () => {
    const result = evaluatePredictiveRuntimePolicy({
      capabilityDecision: packageRequiredDecision,
      prediction: {
        ...packagePrediction,
        action: 'create_draft_pr',
      },
      runtime: {
        githubAccessState: 'ready',
        hasPackage: false,
      },
    });

    const codes = result.violations.map((violation) => violation.code);
    expect(result.allowed).toBe(false);
    expect(codes).toContain('draft_pr_requires_patch_package');
  });

  it('blocks write-like actions without validated GitHub access', () => {
    const result = evaluatePredictiveRuntimePolicy({
      capabilityDecision: {
        route: 'direct-github-patch',
        capability: 'direct_github_patch',
        allowed: false,
        reason: 'GitHub Zugang fehlt.',
        blocker: 'github_access_missing',
        nextAction: 'validate_github_access',
      },
      prediction: {
        action: 'run_direct_patch',
        signal: 'weak',
        confidence: 'low',
        reason: 'Bad prediction that tries to write too early.',
        learnedFrom: 0,
        surfaces: ['router'],
      },
      runtime: {
        githubAccessState: 'missing',
        githubWriteAllowed: false,
      },
    });

    expect(result.allowed).toBe(false);
    expect(result.violations.map((violation) => violation.code)).toContain('github_write_requires_validated_access');
  });

  it('assertPredictiveRuntimePolicy throws on violations', () => {
    expect(() => assertPredictiveRuntimePolicy({
      mode: 'execution',
      capabilityDecision: packageRequiredDecision,
      prediction: packagePrediction,
    })).toThrow(/no_autonomous_write/);
  });
});
