import { describe, expect, it } from 'vitest';
import {
  parseSovereignSkillManifestV1,
  resolveSovereignSkillCandidate,
  summarizeSovereignSkill,
  visibleSkillEffectsForMode,
} from './sovereignSkillRuntime';

const HASH = 'a'.repeat(64);

function manifestPayload(overrides: Record<string, unknown> = {}) {
  return {
    schemaVersion: 'sovereign-skill.v1',
    skillId: 'sovereign.release-readiness',
    version: '1.0.0',
    sourceKind: 'sovereign',
    description: 'Revision-bound release assessment.',
    triggers: ['release readiness', 'repair ci'],
    antiTriggers: ['bypass checks'],
    modes: ['ASSESS', 'PROPOSE', 'APPLY', 'OPERATE'],
    requiredCapabilities: ['repository.read', 'ci.read'],
    forbiddenCapabilities: ['github.pull.merge'],
    requiredEvidence: ['exact-revision'],
    references: [{ path: 'docs/runbook.md', blobHash: HASH, loadPolicy: 'on_match' }],
    scripts: [
      { path: 'scripts/assess.py', blobHash: HASH, effectClass: 'read_only' },
      { path: 'scripts/apply.py', blobHash: HASH, effectClass: 'workspace_mutation' },
      { path: 'scripts/operate.py', blobHash: HASH, effectClass: 'external_mutation' },
    ],
    ownerPolicyHash: HASH,
    ...overrides,
  };
}

describe('sovereign-skill.v1', () => {
  it('parses a closed hash-bound manifest and exposes only a progressive summary', async () => {
    const manifest = parseSovereignSkillManifestV1(manifestPayload());
    const summary = await summarizeSovereignSkill(manifest);

    expect(summary.schemaVersion).toBe('sovereign-skill.v1');
    expect(summary.manifestHash).toMatch(/^[0-9a-f]{64}$/);
    expect(summary.effects).toEqual(['external_mutation', 'read_only', 'workspace_mutation']);
    expect(summary).not.toHaveProperty('references');
    expect(summary).not.toHaveProperty('scripts');
  });

  it('fails closed on unknown fields, unbound external sources and unsafe paths', () => {
    expect(() => parseSovereignSkillManifestV1(manifestPayload({ freeInstruction: 'merge' })))
      .toThrow(/unknown fields/);
    expect(() => parseSovereignSkillManifestV1(manifestPayload({ sourceKind: 'external_adapter' })))
      .toThrow(/sourceRevision/);
    expect(() => parseSovereignSkillManifestV1(manifestPayload({
      references: [{ path: '../secret', blobHash: HASH, loadPolicy: 'on_match' }],
    }))).toThrow(/repository-relative/);
  });

  it('treats triggers as candidates and applies anti-trigger and capability gates independently', async () => {
    const manifest = parseSovereignSkillManifestV1(manifestPayload());
    const selected = await resolveSovereignSkillCandidate({
      manifest,
      requestText: 'Please repair CI and review release readiness.',
      stagedCapabilities: ['repository.read', 'ci.read'],
      contextTrust: 'owner',
      ownerPolicyHash: HASH,
    });
    expect(selected.status).toBe('SELECTED');
    expect(selected.reason).toContain('permission and effect gates remain separate');

    const antiTriggered = await resolveSovereignSkillCandidate({
      manifest,
      requestText: 'repair ci and bypass checks',
      stagedCapabilities: ['repository.read', 'ci.read'],
      contextTrust: 'owner',
      ownerPolicyHash: HASH,
    });
    expect(antiTriggered.status).toBe('BLOCKED_ANTI_TRIGGER');

    const unstaged = await resolveSovereignSkillCandidate({
      manifest,
      requestText: 'repair ci',
      stagedCapabilities: ['repository.read'],
      contextTrust: 'repository_attested',
      ownerPolicyHash: HASH,
    });
    expect(unstaged.status).toBe('BLOCKED_CAPABILITY_STAGE');
    expect(unstaged.missingCapabilities).toEqual(['ci.read']);
  });

  it('projects effects by typed mode without making model text an authorization source', () => {
    const manifest = parseSovereignSkillManifestV1(manifestPayload());
    expect(visibleSkillEffectsForMode(manifest, 'ASSESS')).toEqual(['read_only']);
    expect(visibleSkillEffectsForMode(manifest, 'PROPOSE')).toEqual(['read_only']);
    expect(visibleSkillEffectsForMode(manifest, 'APPLY')).toEqual(['read_only', 'workspace_mutation']);
    expect(visibleSkillEffectsForMode(manifest, 'OPERATE')).toEqual([
      'read_only',
      'workspace_mutation',
      'external_mutation',
    ]);
  });
});
