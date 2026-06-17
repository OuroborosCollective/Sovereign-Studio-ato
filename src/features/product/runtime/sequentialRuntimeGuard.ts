export type SequentialRuntimeStep =
  | 'repo-load'
  | 'package-build'
  | 'diff-load'
  | 'draft-pr-publish'
  | 'workflow-watch'
  | 'repair-plan';

export type SequentialRuntimeStepStatus = 'idle' | 'running' | 'completed' | 'failed' | 'skipped';

export interface SequentialRuntimeStepRecord {
  step: SequentialRuntimeStep;
  status: SequentialRuntimeStepStatus;
  startedAt?: number;
  finishedAt?: number;
  message?: string;
}

export interface SequentialRuntimeEvent {
  sequence: number;
  step: SequentialRuntimeStep;
  status: SequentialRuntimeStepStatus;
  message: string;
  at: number;
}

export interface SequentialRuntimeState {
  activeStep: SequentialRuntimeStep | null;
  steps: Record<SequentialRuntimeStep, SequentialRuntimeStepRecord>;
  history: SequentialRuntimeEvent[];
  sequence: number;
}

export interface SequentialStartOptions {
  repoReady?: boolean;
  hasPackage?: boolean;
  hasDiffSources?: boolean;
  hasDraftCommit?: boolean;
  hasWorkflowReport?: boolean;
}

export interface SequentialRuntimeDecision {
  allowed: boolean;
  reason: string;
}

export const SEQUENTIAL_RUNTIME_STEPS: SequentialRuntimeStep[] = [
  'repo-load',
  'package-build',
  'diff-load',
  'draft-pr-publish',
  'workflow-watch',
  'repair-plan',
];

const STEP_LABELS: Record<SequentialRuntimeStep, string> = {
  'repo-load': 'Repository load',
  'package-build': 'Package build',
  'diff-load': 'Diff source load',
  'draft-pr-publish': 'Draft PR publish',
  'workflow-watch': 'Workflow watch',
  'repair-plan': 'Repair plan',
};

function createStepRecord(step: SequentialRuntimeStep): SequentialRuntimeStepRecord {
  return { step, status: 'idle' };
}

export function createSequentialRuntimeState(): SequentialRuntimeState {
  return {
    activeStep: null,
    steps: Object.fromEntries(SEQUENTIAL_RUNTIME_STEPS.map((step) => [step, createStepRecord(step)])) as Record<SequentialRuntimeStep, SequentialRuntimeStepRecord>,
    history: [],
    sequence: 0,
  };
}

export function describeSequentialStep(step: SequentialRuntimeStep): string {
  return STEP_LABELS[step];
}

function pushEvent(
  state: SequentialRuntimeState,
  step: SequentialRuntimeStep,
  status: SequentialRuntimeStepStatus,
  message: string,
  at: number,
): SequentialRuntimeState {
  const event: SequentialRuntimeEvent = {
    sequence: state.sequence + 1,
    step,
    status,
    message,
    at,
  };
  return {
    ...state,
    sequence: event.sequence,
    history: [...state.history, event].slice(-80),
  };
}

export function canStartSequentialStep(
  state: SequentialRuntimeState,
  step: SequentialRuntimeStep,
  options: SequentialStartOptions = {},
): SequentialRuntimeDecision {
  if (state.activeStep) {
    return {
      allowed: false,
      reason: `${describeSequentialStep(state.activeStep)} is still running. Finish it before starting ${describeSequentialStep(step)}.`,
    };
  }

  if (step !== 'repo-load' && !options.repoReady) {
    return { allowed: false, reason: `${describeSequentialStep(step)} needs a loaded repository snapshot first.` };
  }

  if (step === 'diff-load' && !options.hasPackage) {
    return { allowed: false, reason: 'Diff source load needs a generated package first.' };
  }

  if (step === 'draft-pr-publish' && !options.hasPackage) {
    return { allowed: false, reason: 'Draft PR publish needs a generated package first.' };
  }

  if (step === 'workflow-watch' && !options.hasDraftCommit) {
    return { allowed: false, reason: 'Workflow watch needs a Draft PR commit SHA first.' };
  }

  if (step === 'repair-plan' && !options.hasWorkflowReport) {
    return { allowed: false, reason: 'Repair plan needs a Workflow Watch report first.' };
  }

  return { allowed: true, reason: `${describeSequentialStep(step)} may start.` };
}

export function startSequentialStep(
  state: SequentialRuntimeState,
  step: SequentialRuntimeStep,
  options: SequentialStartOptions = {},
  at = Date.now(),
): SequentialRuntimeState {
  const decision = canStartSequentialStep(state, step, options);
  if (!decision.allowed) {
    throw new Error(decision.reason);
  }

  const next: SequentialRuntimeState = {
    ...state,
    activeStep: step,
    steps: {
      ...state.steps,
      [step]: {
        ...state.steps[step],
        status: 'running',
        startedAt: at,
        finishedAt: undefined,
        message: decision.reason,
      },
    },
  };

  return pushEvent(next, step, 'running', decision.reason, at);
}

export function finishSequentialStep(
  state: SequentialRuntimeState,
  step: SequentialRuntimeStep,
  status: Exclude<SequentialRuntimeStepStatus, 'idle' | 'running'>,
  message: string,
  at = Date.now(),
): SequentialRuntimeState {
  if (state.activeStep !== step) {
    throw new Error(`Cannot finish ${describeSequentialStep(step)} because ${state.activeStep ? describeSequentialStep(state.activeStep) : 'no step'} is active.`);
  }

  const next: SequentialRuntimeState = {
    ...state,
    activeStep: null,
    steps: {
      ...state.steps,
      [step]: {
        ...state.steps[step],
        status,
        finishedAt: at,
        message,
      },
    },
  };

  return pushEvent(next, step, status, message, at);
}

export function resetSequentialRuntime(state: SequentialRuntimeState = createSequentialRuntimeState()): SequentialRuntimeState {
  const reset = createSequentialRuntimeState();
  return {
    ...reset,
    history: state.history,
    sequence: state.sequence,
  };
}

export function summarizeSequentialRuntime(state: SequentialRuntimeState): string {
  const active = state.activeStep ? `${describeSequentialStep(state.activeStep)} running` : 'no active step';
  const completed = SEQUENTIAL_RUNTIME_STEPS.filter((step) => state.steps[step].status === 'completed').length;
  const failed = SEQUENTIAL_RUNTIME_STEPS.filter((step) => state.steps[step].status === 'failed').length;
  return `${active}; ${completed} completed step(s), ${failed} failed step(s).`;
}
