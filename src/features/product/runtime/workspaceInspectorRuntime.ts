import { buildBrownfieldInspectorHint } from './brownfieldInspectorHint';
import { decidePalRoute, type PalAutomationMode } from './palRouter';
import { buildSolutionPatternHint } from './solutionPatternHints';
import type { SolutionPatternStore } from './solutionPatternMemory';
import {
  mergeQuietInspectorSignals,
  type QuietInspectorPolicyResult,
  type QuietInspectorSignal,
} from './quietInspectorHintPolicy';

export interface WorkspaceInspectorRuntimeInput {
  repoName: string;
  branch: string;
  repoFiles: Array<string | { path: string }>;
  mission: string;
  repoReady: boolean;
  blockers?: string[];
  automationMode?: PalAutomationMode;
  solutionPatternStore: SolutionPatternStore;
  now?: number;
}

export interface WorkspaceInspectorRuntimeResult {
  brownfieldScore: number;
  palBlocked: boolean;
  activePatternCount: number;
  policy: QuietInspectorPolicyResult;
}

function visibleSignal(signal: QuietInspectorSignal): QuietInspectorSignal {
  return { ...signal, visible: true };
}

export function buildWorkspaceInspectorRuntime(
  input: WorkspaceInspectorRuntimeInput,
): WorkspaceInspectorRuntimeResult {
  const fileCount = input.repoFiles.length;
  const brownfield = buildBrownfieldInspectorHint({
    repoName: input.repoName,
    branch: input.branch,
    files: input.repoFiles,
    analyzedAt: input.now,
  });
  const pal = decidePalRoute({
    mission: input.mission,
    repoReady: input.repoReady,
    repoFileCount: fileCount,
    blockers: input.blockers,
    automationMode: input.automationMode,
  });
  const memory = buildSolutionPatternHint(input.solutionPatternStore);

  const signals: QuietInspectorSignal[] = [];

  signals.push(visibleSignal({
    id: 'pal',
    source: 'PAL',
    lamp: pal.signal,
    message: pal.reason,
    targetTab: pal.blocked ? 'health' : 'runtime',
    updatedAt: input.now,
  }));

  if (brownfield.visible) {
    signals.push(visibleSignal({
      id: 'brownfield',
      source: 'Brownfield',
      lamp: brownfield.lamp,
      message: brownfield.message,
      targetTab: brownfield.targetTab,
      updatedAt: input.now,
    }));
  }

  if (memory.visible) {
    signals.push(visibleSignal({
      id: 'remote-memory',
      source: 'Remote Memory',
      lamp: 'green',
      message: memory.message,
      targetTab: 'memory',
      updatedAt: input.now,
    }));
  }

  return {
    brownfieldScore: brownfield.report.score.total,
    palBlocked: pal.blocked,
    activePatternCount: memory.activeCount,
    policy: mergeQuietInspectorSignals(signals),
  };
}
