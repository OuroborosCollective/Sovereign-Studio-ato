import { describe, expect, it } from 'vitest';
import { deriveSovereignControlFrameState } from './sovereignControlFrameRuntime';
import { createScanFindingRegistry } from './scanFindingRegistry';
import { createSequentialRuntimeState, startSequentialStep } from './sequentialRuntimeGuard';
import { createSolutionPatternStore } from './solutionPatternMemory';

const common = {
  repoReady: true,
  repoReason: 'Repo ready.',
  repoBusy: false,
  runtimeBusy: false,
  isPublishing: false,
  hasPackage: false,
  hasDiffSources: false,
  isWatchingWorkflow: false,
  workflowReport: null,
  solutionPatternStore: createSolutionPatternStore(),
  scanRegistry: createScanFindingRegistry(),
  remoteMemoryBusy: false,
  remoteMemoryReady: false,
  restoredSessionReady: false,
  telemetryCount: 0,
  nowMs: 100000,
  lastUserInteractionAt: 0,
};

describe('sovereignControlFrameRuntime', () => {
  it('derives stable module order', () => {
    const state = deriveSovereignControlFrameState({
      ...common,
      sequentialRuntime: createSequentialRuntimeState(),
    });

    expect(state.modules.map((module) => module.id)).toEqual([
      'init',
      'router',
      'pattern',
      'sync',
      'orchestr',
      'session',
      'logger',
      'restore',
    ]);
    expect(state.modules.find((module) => module.id === 'init')?.signal).toBe('active');
  });

  it('marks orchestr as processing during a sequential step', () => {
    const sequentialRuntime = startSequentialStep(createSequentialRuntimeState(), 'package-build', {
      repoReady: true,
      hasPackage: false,
      hasDiffSources: false,
      hasDraftCommit: false,
      hasWorkflowReport: false,
    });

    const state = deriveSovereignControlFrameState({
      ...common,
      runtimeBusy: true,
      sequentialRuntime,
      agentJob: { status: 'running', changedFiles: [], events: [] },
    });

    expect(state.activeModuleId).toBe('orchestr');
    expect(state.modules.find((module) => module.id === 'orchestr')?.signal).toBe('processing');
  });

  it('marks recent user interaction as router override', () => {
    const state = deriveSovereignControlFrameState({
      ...common,
      sequentialRuntime: createSequentialRuntimeState(),
      nowMs: 60_000,
      lastUserInteractionAt: 45_000,
    });

    expect(state.overrideActive).toBe(true);
    expect(state.modules.find((module) => module.id === 'router')?.signal).toBe('warning');
  });
});
