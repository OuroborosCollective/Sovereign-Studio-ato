import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { JobPhase } from '../types/domain';
import { projectRunAndJobPhase } from './runtimePhaseProjection';

const phases: JobPhase[] = [
  'IDLE', 'AWAKENING', 'DISPATCHING', 'PROVISIONING', 'EXECUTING',
  'AWAITING_OWNER_INPUT', 'FINALIZING', 'BLOCKED', 'READY_TO_PUBLISH',
  'COMPLETED', 'FAILED', 'CANCELLED',
];

describe('persisted run owns blocking and owner-input phase projection', () => {
  it.each(['BLOCKED', 'FAILED', 'CANCELLED', 'AWAITING_OWNER_INPUT'] as JobPhase[])(
    'never lets any linked job override %s', runPhase => {
      for (const jobPhase of phases) expect(projectRunAndJobPhase(runPhase, jobPhase)).toBe(runPhase);
    },
  );

  it('reproduces the actual blocked-run/running-job contradiction from live run 34412028973', () => {
    // Recorded HTTP facts: run BLOCKED / COMPLETE_SINGLE_AGENT_WORKSPACE_EVIDENCE,
    // while the linked implementation job repeatedly returned running. No live success fixture.
    expect(projectRunAndJobPhase('BLOCKED', 'EXECUTING')).toBe('BLOCKED');
    expect(projectRunAndJobPhase('BLOCKED', 'COMPLETED')).not.toBe('COMPLETED');
    expect(projectRunAndJobPhase('BLOCKED', 'READY_TO_PUBLISH')).not.toBe('READY_TO_PUBLISH');
  });

  it('preserves ordinary linked-job projections when no run blocker exists', () => {
    for (const jobPhase of phases) expect(projectRunAndJobPhase('EXECUTING', jobPhase)).toBe(jobPhase);
    expect(projectRunAndJobPhase('DISPATCHING', 'PROVISIONING')).toBe('PROVISIONING');
    expect(projectRunAndJobPhase('COMPLETED', 'READY_TO_PUBLISH')).toBe('READY_TO_PUBLISH');
  });

  it('uses the tested projection at the actual production adapter boundary', () => {
    const adapter = readFileSync('src/features/control-surface-vnext/adapter/production-adapter.ts', 'utf8');
    expect(adapter).toContain("import { projectRunAndJobPhase } from '../fsm/runtimePhaseProjection'");
    expect(adapter).toContain('const phase = projectRunAndJobPhase(');
    expect(adapter).toContain('phase: projectRunAndJobPhase(runPhase, publication');
    expect(adapter).toContain('snapshot ? phaseFromJob(snapshot, run) : runPhase');
    expect(adapter).toContain("runPhase === 'BLOCKED' || runPhase === 'FAILED'");
    expect(adapter).not.toContain("const phase = runPhase === 'AWAITING_OWNER_INPUT'");
  });
});
