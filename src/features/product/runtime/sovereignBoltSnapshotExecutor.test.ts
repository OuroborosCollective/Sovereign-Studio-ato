import { describe, expect, it } from 'vitest';
import {
  BOLT_SNAPSHOT_RESULT_SCHEMA,
  buildBoltCapabilityProbePlan,
  buildBoltSnapshotJob,
  resolveObservedBoltCapabilities,
  validateBoltSnapshotResult,
  validateBoltSnapshotSource,
} from './sovereignBoltSnapshotExecutor';

const REVISION = '0123456789abcdef0123456789abcdef01234567';

describe('sovereignBoltSnapshotExecutor', () => {
  it('fails closed when a floating branch name is used as revision authority', () => {
    const validation = validateBoltSnapshotSource({
      repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
      revision: 'main',
      archiveFormat: 'zip',
    });

    expect(validation.allowed).toBe(false);
    expect(validation.blockers.join(' ')).toContain('exact 40-character lowercase Git revision');
  });

  it('only exposes capabilities that were positively observed with evidence', () => {
    expect(resolveObservedBoltCapabilities([
      { capability: 'python', available: true, evidence: 'Python 3.12.4' },
      { capability: 'blender-headless', available: true, evidence: 'Blender 4.3.2 background mode' },
      { capability: 'ninja', available: false, evidence: 'not found' },
      { capability: 'gamedev-tools', available: true, evidence: '' },
    ])).toEqual(['blender-headless', 'python']);
  });

  it('builds a revision-bound Draft-PR-only job with zero production authority', () => {
    const job = buildBoltSnapshotJob({
      repoFullName: 'OuroborosCollective/Echoes_of_Aurion',
      branch: 'main',
      revision: REVISION,
      observations: [
        { capability: 'python', available: true, evidence: 'Python 3.12.4' },
        { capability: 'blender-headless', available: true, evidence: 'Blender 4.3.2' },
      ],
    });

    expect(job.executor).toBe('bolt-diy-snapshot');
    expect(job.snapshotKey).toBe(`OuroborosCollective/Echoes_of_Aurion@${REVISION}`);
    expect(job.expectedArchiveName).toContain(REVISION.slice(0, 12));
    expect(job.draftPrOnly).toBe(true);
    expect(job.authority).toEqual({
      production: false,
      rawVps: false,
      rawDatabase: false,
      gameplayMutation: false,
      githubDirectMerge: false,
    });
  });

  it('rejects a returned bundle from the wrong source revision', () => {
    const job = buildBoltSnapshotJob({
      repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
      revision: REVISION,
    });

    const validation = validateBoltSnapshotResult(job, {
      schema: BOLT_SNAPSHOT_RESULT_SCHEMA,
      sourceRevision: '89abcdef0123456789abcdef0123456789abcdef',
      changedFiles: ['src/features/product/runtime/foo.ts'],
      evidence: [
        { kind: 'snapshot-provenance', passed: true, summary: 'archive manifest matches' },
        { kind: 'diff', passed: true, summary: '1 file changed' },
        { kind: 'tests', passed: true, summary: '12 passed' },
      ],
    });

    expect(validation.allowed).toBe(false);
    expect(validation.blockers.join(' ')).toContain('revision does not match');
  });

  it('rejects unsafe changed paths and missing mandatory evidence', () => {
    const job = buildBoltSnapshotJob({
      repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
      revision: REVISION,
    });

    const validation = validateBoltSnapshotResult(job, {
      schema: BOLT_SNAPSHOT_RESULT_SCHEMA,
      sourceRevision: REVISION,
      changedFiles: ['../secret.env'],
      evidence: [
        { kind: 'snapshot-provenance', passed: true, summary: 'archive manifest matches' },
        { kind: 'diff', passed: true, summary: 'diff exists' },
      ],
    });

    expect(validation.allowed).toBe(false);
    expect(validation.blockers).toContain('Bolt result contains an unsafe changed-file path.');
    expect(validation.blockers).toContain('Bolt result is missing required evidence: tests.');
  });

  it('accepts only exact-revision results with all required evidence green', () => {
    const job = buildBoltSnapshotJob({
      repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
      revision: REVISION,
      requiredEvidence: ['snapshot-provenance', 'diff', 'tests', 'build'],
    });

    const validation = validateBoltSnapshotResult(job, {
      schema: BOLT_SNAPSHOT_RESULT_SCHEMA,
      sourceRevision: REVISION,
      changedFiles: [
        'src/features/product/runtime/sovereignBoltSnapshotExecutor.ts',
        'src/features/product/runtime/sovereignBoltSnapshotExecutor.test.ts',
      ],
      evidence: [
        { kind: 'snapshot-provenance', passed: true, summary: 'revision exact' },
        { kind: 'diff', passed: true, summary: '2 files changed' },
        { kind: 'tests', passed: true, summary: 'focused suite passed' },
        { kind: 'build', passed: true, summary: 'typecheck passed' },
      ],
    });

    expect(validation.allowed).toBe(true);
    expect(validation.blockers).toEqual([]);
  });

  it('publishes a concrete add-on probe plan without claiming probe success', () => {
    const plan = buildBoltCapabilityProbePlan();

    expect(plan.python[0]).toContain('python');
    expect(plan['blender-headless'][0]).toContain('blender --background');
    expect(plan.ninja[0]).toContain('ninja --version');
    expect(plan['gamedev-tools'].length).toBeGreaterThan(0);
  });
});
