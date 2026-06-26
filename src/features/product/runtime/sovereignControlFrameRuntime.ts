import type {
  SovereignControlConditionStatus,
  SovereignControlFrameModuleId,
  SovereignControlPhase,
  SovereignControlSignal,
} from './sovereignControlFrameContract';
import type { ScanFindingRegistry } from './scanFindingRegistry';
import type { SequentialRuntimeState } from './sequentialRuntimeGuard';
import type { SolutionPatternStore } from './solutionPatternMemory';
import type { WorkflowWatchReport } from './workflowWatch';
import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';

export interface SovereignControlCondition {
  readonly label: string;
  readonly status: SovereignControlConditionStatus;
}

export interface SovereignControlModuleState {
  readonly id: SovereignControlFrameModuleId;
  readonly signal: SovereignControlSignal;
  readonly phase: SovereignControlPhase;
  readonly conditions: readonly SovereignControlCondition[];
  readonly detail: string;
}

export interface SovereignControlLogLine {
  readonly level: 'debug' | 'info' | 'warn' | 'error' | 'signal';
  readonly moduleId: SovereignControlFrameModuleId | 'system';
  readonly message: string;
}

export interface SovereignControlFrameStateInput {
  readonly repoReady: boolean;
  readonly repoReason: string;
  readonly repoBusy: boolean;
  readonly runtimeBusy: boolean;
  readonly isPublishing: boolean;
  readonly hasPackage: boolean;
  readonly hasDiffSources: boolean;
  readonly isWatchingWorkflow: boolean;
  readonly workflowReport: WorkflowWatchReport | null;
  readonly sequentialRuntime: SequentialRuntimeState;
  readonly solutionPatternStore: SolutionPatternStore;
  readonly scanRegistry: ScanFindingRegistry;
  readonly openhandsJob?: OpenHandsJobSnapshot;
  readonly remoteMemoryBusy?: boolean;
  readonly remoteMemoryReady?: boolean;
  readonly restoredSessionReady?: boolean;
  readonly telemetryCount?: number;
  readonly lastUserInteractionAt?: number;
  readonly nowMs?: number;
}

export interface SovereignControlFrameState {
  readonly activeModuleId: SovereignControlFrameModuleId;
  readonly modules: readonly SovereignControlModuleState[];
  readonly logs: readonly SovereignControlLogLine[];
  readonly signalSummary: string;
  readonly sessionSummary: string;
  readonly activePatternCount: number;
  readonly confidence: number;
  readonly overrideActive: boolean;
}

function condition(label: string, status: SovereignControlConditionStatus): SovereignControlCondition {
  return { label, status };
}

function signalFromBusy(ok: boolean, busy: boolean, error: boolean): SovereignControlSignal {
  if (error) return 'error';
  if (busy) return 'processing';
  return ok ? 'active' : 'warning';
}

function phaseFromSignal(signal: SovereignControlSignal): SovereignControlPhase {
  if (signal === 'error') return 'error';
  if (signal === 'processing') return 'working';
  if (signal === 'active') return 'done';
  if (signal === 'warning') return 'spinup';
  return 'idle';
}

function activePatternCount(store: SolutionPatternStore): number {
  return Array.isArray(store.patterns) ? store.patterns.filter((pattern) => pattern.status === 'active').length : 0;
}

function scanFindingCount(registry: ScanFindingRegistry): number {
  const values = Object.values(registry.sources ?? {});
  return values.reduce((sum, source) => sum + (Array.isArray(source.findings) ? source.findings.length : 0), 0);
}

function activeStepId(runtime: SequentialRuntimeState): string {
  return runtime.activeStep ?? 'idle';
}

function openHandsError(job: OpenHandsJobSnapshot | undefined): boolean {
  return job?.status === 'failed' || job?.status === 'blocked';
}

function workflowError(report: WorkflowWatchReport | null): boolean {
  return report?.status === 'red';
}

function repoModule(input: SovereignControlFrameStateInput): SovereignControlModuleState {
  const signal = signalFromBusy(input.repoReady, input.repoBusy, !input.repoReady && input.repoReason.toLowerCase().includes('fehler'));
  return {
    id: 'init',
    signal,
    phase: phaseFromSignal(signal),
    detail: input.repoReason,
    conditions: [
      condition('Repo snapshot ready', input.repoReady ? 'pass' : 'wait'),
      condition('Repo loader idle', input.repoBusy ? 'wait' : 'pass'),
      condition('Repo reason available', input.repoReason.trim() ? 'pass' : 'fail'),
    ],
  };
}

function routerModule(input: SovereignControlFrameStateInput): SovereignControlModuleState {
  const overrideActive = input.lastUserInteractionAt && input.nowMs ? input.nowMs - input.lastUserInteractionAt < 30_000 : false;
  const signal: SovereignControlSignal = input.runtimeBusy ? 'processing' : overrideActive ? 'warning' : 'active';
  return {
    id: 'router',
    signal,
    phase: phaseFromSignal(signal),
    detail: overrideActive ? 'Manual override window active.' : 'Auto-view router is clear.',
    conditions: [
      condition('Runtime step known', activeStepId(input.sequentialRuntime) ? 'pass' : 'fail'),
      condition('No passive hijack', 'pass'),
      condition('Manual override clear', overrideActive ? 'wait' : 'pass'),
    ],
  };
}

function patternModule(input: SovereignControlFrameStateInput, patterns: number): SovereignControlModuleState {
  const signal: SovereignControlSignal = patterns > 0 ? 'active' : 'idle';
  return {
    id: 'pattern',
    signal,
    phase: phaseFromSignal(signal),
    detail: `${patterns} active pattern(s).`,
    conditions: [
      condition('Pattern store readable', Array.isArray(input.solutionPatternStore.patterns) ? 'pass' : 'fail'),
      condition('Active patterns available', patterns > 0 ? 'pass' : 'wait'),
      condition('Patterns are runtime-derived', 'pass'),
    ],
  };
}

function syncModule(input: SovereignControlFrameStateInput): SovereignControlModuleState {
  const signal = signalFromBusy(Boolean(input.remoteMemoryReady), Boolean(input.remoteMemoryBusy), false);
  return {
    id: 'sync',
    signal,
    phase: phaseFromSignal(signal),
    detail: input.remoteMemoryReady ? 'Remote memory gateway ready.' : 'Remote memory gateway not confirmed.',
    conditions: [
      condition('Gateway config present', input.remoteMemoryReady ? 'pass' : 'wait'),
      condition('Sync idle', input.remoteMemoryBusy ? 'wait' : 'pass'),
      condition('No self-hosted HTTP default required', 'pass'),
    ],
  };
}

function orchestrModule(input: SovereignControlFrameStateInput): SovereignControlModuleState {
  const error = openHandsError(input.openhandsJob);
  const busy = input.runtimeBusy || input.isPublishing || input.openhandsJob?.status === 'running';
  const ok = input.hasPackage || input.openhandsJob?.status === 'completed';
  const signal = signalFromBusy(Boolean(ok), busy, error);
  return {
    id: 'orchestr',
    signal,
    phase: phaseFromSignal(signal),
    detail: `Step: ${activeStepId(input.sequentialRuntime)} · OpenHands: ${input.openhandsJob?.status ?? 'idle'}`,
    conditions: [
      condition('Sequential runtime present', input.sequentialRuntime ? 'pass' : 'fail'),
      condition('OpenHands not blocked', error ? 'fail' : 'pass'),
      condition('Package or job result available', ok ? 'pass' : busy ? 'wait' : 'wait'),
    ],
  };
}

function sessionModule(input: SovereignControlFrameStateInput): SovereignControlModuleState {
  const signal: SovereignControlSignal = input.restoredSessionReady ? 'active' : 'idle';
  return {
    id: 'session',
    signal,
    phase: phaseFromSignal(signal),
    detail: input.restoredSessionReady ? 'Session snapshot available.' : 'No restored session snapshot confirmed.',
    conditions: [
      condition('Session memory API present', 'pass'),
      condition('Snapshot ready', input.restoredSessionReady ? 'pass' : 'wait'),
      condition('Restore does not mutate repo silently', 'pass'),
    ],
  };
}

function loggerModule(input: SovereignControlFrameStateInput, findings: number): SovereignControlModuleState {
  const count = input.telemetryCount ?? 0;
  const signal: SovereignControlSignal = findings > 0 ? 'warning' : count > 0 ? 'active' : 'idle';
  return {
    id: 'logger',
    signal,
    phase: phaseFromSignal(signal),
    detail: `${count} telemetry item(s), ${findings} finding(s).`,
    conditions: [
      condition('Telemetry counter available', count >= 0 ? 'pass' : 'fail'),
      condition('Scan registry readable', findings >= 0 ? 'pass' : 'fail'),
      condition('No token log required', 'pass'),
    ],
  };
}

function restoreModule(input: SovereignControlFrameStateInput): SovereignControlModuleState {
  const signal: SovereignControlSignal = input.restoredSessionReady ? 'active' : 'idle';
  return {
    id: 'restore',
    signal,
    phase: phaseFromSignal(signal),
    detail: input.restoredSessionReady ? 'Restore snapshot can be inspected.' : 'Restore waits for explicit user action.',
    conditions: [
      condition('Restore explicit only', 'pass'),
      condition('Clear view explicit only', 'pass'),
      condition('Snapshot found', input.restoredSessionReady ? 'pass' : 'wait'),
    ],
  };
}

export function deriveSovereignControlFrameState(input: SovereignControlFrameStateInput): SovereignControlFrameState {
  const patterns = activePatternCount(input.solutionPatternStore);
  const findings = scanFindingCount(input.scanRegistry);
  const overrideActive = Boolean(input.lastUserInteractionAt && input.nowMs && input.nowMs - input.lastUserInteractionAt < 30_000);
  const modules: SovereignControlModuleState[] = [
    repoModule(input),
    routerModule(input),
    patternModule(input, patterns),
    syncModule(input),
    orchestrModule(input),
    sessionModule(input),
    loggerModule(input, findings),
    restoreModule(input),
  ];

  const activeModule = modules.find((module) => module.signal === 'error')
    ?? modules.find((module) => module.signal === 'processing')
    ?? modules.find((module) => module.signal === 'warning')
    ?? modules.find((module) => module.signal === 'active')
    ?? modules[0];

  const logs: SovereignControlLogLine[] = modules
    .filter((module) => module.signal !== 'idle')
    .map((module) => ({
      level: module.signal === 'error' ? 'error' : module.signal === 'warning' ? 'warn' : module.signal === 'processing' ? 'signal' : 'info',
      moduleId: module.id,
      message: module.detail,
    }));

  return {
    activeModuleId: activeModule.id,
    modules,
    logs,
    signalSummary: `${modules.filter((module) => module.signal === 'processing').length} processing · ${modules.filter((module) => module.signal === 'warning').length} warning · ${modules.filter((module) => module.signal === 'error').length} error`,
    sessionSummary: `step=${activeStepId(input.sequentialRuntime)} · package=${input.hasPackage ? 'yes' : 'no'} · diff=${input.hasDiffSources ? 'yes' : 'no'}`,
    activePatternCount: patterns,
    confidence: Math.min(1, Math.max(0, (patterns > 0 ? 0.25 : 0) + (input.repoReady ? 0.25 : 0) + (input.hasPackage ? 0.25 : 0) + (input.hasDiffSources ? 0.25 : 0))),
    overrideActive,
  };
}
