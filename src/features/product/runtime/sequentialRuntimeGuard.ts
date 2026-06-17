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

export interface SequentialRuntimeValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
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

export function validateSequentialRuntimeState(state: SequentialRuntimeState): SequentialRuntimeValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const knownSteps = new Set(SEQUENTIAL_RUNTIME_STEPS);

  for (const step of SEQUENTIAL_RUNTIME_STEPS) {
    const record = state.steps[step];
    if (!record) {
      errors.push(`Missing step record: ${step}`);
      continue;
    }
    if (record.step !== step) {
      errors.push(`Step record mismatch: expected ${step}, got ${record.step}`);
    }
    if (record.status === 'running' && !record.startedAt) {
      warnings.push(`${describeSequentialStep(step)} is running without a start timestamp.`);
    }
    if ((record.status === 'completed' || record.status === 'failed' || record.status === 'skipped') && !record.finishedAt) {
      warnings.push(`${describeSequentialStep(step)} is ${record.status} without a finish timestamp.`);
    }
  }

  const runningSteps = SEQUENTIAL_RUNTIME_STEPS.filter((step) => state.steps[step]?.status === 'running');
  if (runningSteps.length > 1) {
    errors.push(`More than one runtime step is running: ${runningSteps.join(', ')}`);
  }

  if (state.activeStep && !knownSteps.has(state.activeStep)) {
    errors.push(`Unknown active step: ${state.activeStep}`);
  }

  if (state.activeStep && state.steps[state.activeStep]?.status !== 'running') {
    errors.push(`Active step ${state.activeStep} is not marked as running.`);
  }

  if (!state.activeStep && runningSteps.length > 0) {
    errors.push(`Running step exists without activeStep: ${runningSteps.join(', ')}`);
  }

  if (state.activeStep && runningSteps.length === 0) {
    errors.push(`activeStep is ${state.activeStep}, but no step is running.`);
  }

  let previousSequence = 0;
  for (const event of state.history) {
    if (!knownSteps.has(event.step)) {
      errors.push(`History contains unknown step: ${event.step}`);
    }
    if (event.sequence <= previousSequence) {
      errors.push('History sequence is not strictly increasing.');
      break;
    }
    previousSequence = event.sequence;
  }

  if (state.history.length && state.sequence !== state.history[state.history.length - 1]?.sequence) {
    warnings.push('State sequence does not match latest history event.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in sequential runtime state.`,
  };
}

export function assertSequentialRuntimeStateValid(state: SequentialRuntimeState): void {
  const report = validateSequentialRuntimeState(state);
  if (!report.valid) {
    throw new Error(`Sequential runtime state is invalid: ${report.errors.join(' | ')}`);
  }
}

export function canStartSequentialStep(
  state: SequentialRuntimeState,
  step: SequentialRuntimeStep,
  options: SequentialStartOptions = {},
): SequentialRuntimeDecision {
  assertSequentialRuntimeStateValid(state);

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

export function validateSequentialRuntimeStepRequest(
  state: SequentialRuntimeState,
  step: SequentialRuntimeStep,
  options: SequentialStartOptions = {},
): SequentialRuntimeValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!SEQUENTIAL_RUNTIME_STEPS.includes(step)) {
    errors.push(`Unknown sequential runtime step: ${step}`);
  }

  const stateReport = validateSequentialRuntimeState(state);
  errors.push(...stateReport.errors.map((error) => `state: ${error}`));
  warnings.push(...stateReport.warnings.map((warning) => `state: ${warning}`));

  if (!errors.length) {
    const decision = canStartSequentialStep(state, step, options);
    if (!decision.allowed) errors.push(decision.reason);
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) before starting ${describeSequentialStep(step)}.`,
  };
}

export function assertSequentialRuntimeStepRequestValid(
  state: SequentialRuntimeState,
  step: SequentialRuntimeStep,
  options: SequentialStartOptions = {},
): void {
  const report = validateSequentialRuntimeStepRequest(state, step, options);
  if (!report.valid) {
    throw new Error(`Sequential runtime step request is invalid: ${report.errors.join(' | ')}`);
  }
}

export function startSequentialStep(
  state: SequentialRuntimeState,
  step: SequentialRuntimeStep,
  options: SequentialStartOptions = {},
  at = Date.now(),
): SequentialRuntimeState {
  assertSequentialRuntimeStepRequestValid(state, step, options);
  const decision = canStartSequentialStep(state, step, options);

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

  const withEvent = pushEvent(next, step, 'running', decision.reason, at);
  assertSequentialRuntimeStateValid(withEvent);
  return withEvent;
}

export function finishSequentialStep(
  state: SequentialRuntimeState,
  step: SequentialRuntimeStep,
  status: Exclude<SequentialRuntimeStepStatus, 'idle' | 'running'>,
  message: string,
  at = Date.now(),
): SequentialRuntimeState {
  assertSequentialRuntimeStateValid(state);

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

  const withEvent = pushEvent(next, step, status, message, at);
  assertSequentialRuntimeStateValid(withEvent);
  return withEvent;
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
