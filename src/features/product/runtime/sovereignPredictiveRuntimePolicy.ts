import type { CapabilityDecision } from './sovereignCapabilityTypes';
import type { SovereignActionEventInput } from './sovereignActionStreamRuntime';
import type {
  PredictiveActionDecision,
  PredictiveInspectorSignal,
  PredictiveMenuSuggestion,
  PredictiveSurface,
} from './sovereignPredictiveActionRuntime';

export type PredictiveRuntimePolicyCode =
  | 'no_secret_learning'
  | 'no_ui_truth'
  | 'no_autonomous_write'
  | 'no_gate_bypass'
  | 'learn_only_from_runtime_events'
  | 'prediction_requires_blocker_or_signal'
  | 'unknown_action_blocks'
  | 'unknown_surface_blocks'
  | 'draft_pr_requires_patch_package'
  | 'github_write_requires_validated_access'
  | 'agent_job_requires_repo'
  | 'agent_job_requires_validated_github_access_for_write'
  | 'agent_job_requires_workspace_policy'
  | 'agent_tool_requires_backend_state'
  | 'agent_result_requires_evidence'
  | 'agent_cleanup_required_after_terminal_state';

export type PredictiveRuntimePolicyMode = 'suggestion' | 'execution';

export interface PredictiveRuntimePolicyViolation {
  readonly code: PredictiveRuntimePolicyCode;
  readonly message: string;
}

export interface PredictiveRuntimeContext {
  readonly repoReady?: boolean;
  readonly githubAccessState?: 'missing' | 'requested' | 'validating' | 'ready' | 'invalid' | 'failed';
  readonly githubWriteAllowed?: boolean;
  readonly hasPackage?: boolean;
  readonly agentJobStatus?: 'idle' | 'queued' | 'provisioning' | 'running' | 'validating' | 'completed' | 'failed' | 'blocked' | 'cleaned';
  readonly workspaceReady?: boolean;
  readonly hasEvidence?: boolean;
  readonly hasTerminalResult?: boolean;
  readonly backendAgentStateReady?: boolean;
}

export interface PredictiveRuntimePolicyInput {
  readonly mode?: PredictiveRuntimePolicyMode;
  readonly capabilityDecision?: CapabilityDecision | null;
  readonly prediction?: PredictiveActionDecision | null;
  readonly actionEvent?: SovereignActionEventInput | null;
  readonly menuSuggestions?: readonly PredictiveMenuSuggestion[];
  readonly inspectorSignals?: readonly PredictiveInspectorSignal[];
  readonly runtime?: PredictiveRuntimeContext;
}

export interface PredictiveRuntimePolicyResult {
  readonly allowed: boolean;
  readonly checkedPolicies: readonly PredictiveRuntimePolicyCode[];
  readonly violations: readonly PredictiveRuntimePolicyViolation[];
}

const CHECKED_POLICIES: readonly PredictiveRuntimePolicyCode[] = [
  'no_secret_learning',
  'no_ui_truth',
  'no_autonomous_write',
  'no_gate_bypass',
  'learn_only_from_runtime_events',
  'prediction_requires_blocker_or_signal',
  'unknown_action_blocks',
  'unknown_surface_blocks',
  'draft_pr_requires_patch_package',
  'github_write_requires_validated_access',
  'agent_job_requires_repo',
  'agent_job_requires_validated_github_access_for_write',
  'agent_job_requires_workspace_policy',
  'agent_tool_requires_backend_state',
  'agent_result_requires_evidence',
  'agent_cleanup_required_after_terminal_state',
];

const ALLOWED_ACTIONS = new Set([
  'ask_user',
  'load_repo',
  'validate_github_access',
  'generate_patch_package',
  'run_worker',
  'run_direct_patch',
  'start_workspace',
  'start_openhands',
  'create_draft_pr',
  'show_blocker',
  'create_agent_job',
  'provision_agent_workspace',
  'run_agent_tool',
  'validate_agent_result',
  'prepare_agent_draft_pr',
  'learn_agent_pattern',
  'cleanup_agent_workspace',
]);

const ALLOWED_SURFACES: ReadonlySet<PredictiveSurface> = new Set([
  'router',
  'action_stream',
  'menu',
  'inspector',
  'github_access',
  'worker',
  'executor',
  'draft_pr',
  'repo',
  'toolchain',
  'runtime',
  'agent_job',
  'agent_workspace',
  'agent_tool',
  'agent_evidence',
  'agent_pattern',
]);

const WRITE_LIKE_ACTIONS = new Set([
  'run_direct_patch',
  'start_openhands',
  'start_workspace',
  'create_draft_pr',
  'create_agent_job',
  'prepare_agent_draft_pr',
]);

const AGENT_ACTIONS = new Set([
  'create_agent_job',
  'provision_agent_workspace',
  'run_agent_tool',
  'validate_agent_result',
  'prepare_agent_draft_pr',
  'learn_agent_pattern',
  'cleanup_agent_workspace',
]);

const SECRET_PATTERN = /(?:github_pat_[A-Za-z0-9_]{10,}|gh[pousr]_[A-Za-z0-9_]{10,}|GITHUB_(?:TOKEN|CLIENT_SECRET|PAT)|client_secret|Authorization:\s*Bearer\s+[^\s]+)/i;

function containsSecret(value: unknown): boolean {
  try {
    return SECRET_PATTERN.test(JSON.stringify(value));
  } catch {
    return true;
  }
}

function pushViolation(
  violations: PredictiveRuntimePolicyViolation[],
  code: PredictiveRuntimePolicyCode,
  message: string,
): void {
  violations.push({ code, message });
}

function validateSurfaces(
  violations: PredictiveRuntimePolicyViolation[],
  input: PredictiveRuntimePolicyInput,
): void {
  const surfaces: unknown[] = [
    ...(input.prediction?.surfaces ?? []),
    ...(input.menuSuggestions ?? []).map((suggestion) => suggestion.surface),
    ...(input.inspectorSignals ?? []).map((signal) => signal.surface),
  ];

  for (const surface of surfaces) {
    if (typeof surface !== 'string' || !ALLOWED_SURFACES.has(surface as PredictiveSurface)) {
      pushViolation(
        violations,
        'unknown_surface_blocks',
        `Predictive Runtime blockiert unbekannte Oberfläche: ${String(surface)}.`,
      );
    }
  }
}

function validateAgentPrediction(
  violations: PredictiveRuntimePolicyViolation[],
  prediction: PredictiveActionDecision,
  runtime: PredictiveRuntimeContext,
): void {
  if (!AGENT_ACTIONS.has(prediction.action)) return;

  if (prediction.action === 'create_agent_job' && runtime.repoReady !== true) {
    pushViolation(
      violations,
      'agent_job_requires_repo',
      'Agent Job darf erst vorgeschlagen werden, wenn Repo-Kontext geladen und geprüft ist.',
    );
  }

  if (prediction.action === 'create_agent_job' && runtime.githubAccessState && runtime.githubAccessState !== 'ready') {
    pushViolation(
      violations,
      'agent_job_requires_validated_github_access_for_write',
      'Agent Job mit Schreib-/Repo-Pfad braucht validierten GitHub-Zugang.',
    );
  }

  if (prediction.action === 'provision_agent_workspace' && runtime.agentJobStatus !== 'queued' && runtime.agentJobStatus !== 'provisioning') {
    pushViolation(
      violations,
      'agent_job_requires_workspace_policy',
      'Agent Workspace darf nur aus einem echten queued/provisioning Agent-Job-State vorbereitet werden.',
    );
  }

  if (prediction.action === 'run_agent_tool') {
    if (runtime.backendAgentStateReady === false || runtime.agentJobStatus === 'idle' || !runtime.agentJobStatus) {
      pushViolation(
        violations,
        'agent_tool_requires_backend_state',
        'Agent Tool braucht einen gespeicherten Backend-Agent-Job-State.',
      );
    }
    if (runtime.workspaceReady !== true) {
      pushViolation(
        violations,
        'agent_job_requires_workspace_policy',
        'Agent Tool darf ohne geprüften Workspace-State nicht laufen.',
      );
    }
  }

  if ((prediction.action === 'validate_agent_result' || prediction.action === 'prepare_agent_draft_pr' || prediction.action === 'learn_agent_pattern') && runtime.hasEvidence !== true) {
    pushViolation(
      violations,
      'agent_result_requires_evidence',
      'Agent Ergebnis braucht changedFiles, diffSummary, testSummary oder blockerReason als Runtime-Evidence.',
    );
  }

  if (prediction.action === 'cleanup_agent_workspace' && runtime.hasTerminalResult !== true) {
    pushViolation(
      violations,
      'agent_cleanup_required_after_terminal_state',
      'Agent Workspace Cleanup ist erst nach terminalem Agent-State erlaubt.',
    );
  }
}

export function evaluatePredictiveRuntimePolicy(
  input: PredictiveRuntimePolicyInput,
): PredictiveRuntimePolicyResult {
  const violations: PredictiveRuntimePolicyViolation[] = [];
  const mode = input.mode ?? 'suggestion';
  const prediction = input.prediction ?? null;
  const runtime = input.runtime ?? {};

  if (containsSecret(input)) {
    pushViolation(
      violations,
      'no_secret_learning',
      'Predictive Runtime darf keine Tokens, Client-Secrets oder Secret-ähnliche Werte lernen, speichern oder ausgeben.',
    );
  }

  if (mode === 'execution') {
    pushViolation(
      violations,
      'no_autonomous_write',
      'Predictive Runtime darf nicht selbst ausführen; sie darf nur nächste erlaubte Runtime-Aktionen vorschlagen.',
    );
  }

  if (prediction) {
    if (!ALLOWED_ACTIONS.has(prediction.action)) {
      pushViolation(
        violations,
        'unknown_action_blocks',
        `Predictive Runtime blockiert unbekannte Aktion: ${String(prediction.action)}.`,
      );
    }

    if (prediction.signal !== 'none' && !input.capabilityDecision?.blocker) {
      pushViolation(
        violations,
        'prediction_requires_blocker_or_signal',
        'Eine aktive Prediction braucht einen echten Router-Blocker oder ein Runtime-Signal als Ursache.',
      );
    }

    if (
      input.capabilityDecision?.blocker === 'package_required'
      && prediction.action !== 'generate_patch_package'
    ) {
      pushViolation(
        violations,
        'draft_pr_requires_patch_package',
        'package_required darf nur zur nächsten Aktion generate_patch_package führen.',
      );
    }

    if (prediction.action === 'create_draft_pr' && runtime.hasPackage === false) {
      pushViolation(
        violations,
        'draft_pr_requires_patch_package',
        'Draft PR darf ohne vorhandenes Patch-Paket/Diff nicht vorgeschlagen werden.',
      );
    }

    if (
      WRITE_LIKE_ACTIONS.has(prediction.action)
      && runtime.githubAccessState
      && runtime.githubAccessState !== 'ready'
    ) {
      pushViolation(
        violations,
        'github_write_requires_validated_access',
        'Write-ähnliche Aktionen brauchen validierten GitHub-Zugang.',
      );
    }

    validateAgentPrediction(violations, prediction, runtime);
  }

  validateSurfaces(violations, input);

  if (input.actionEvent?.state === 'done' && prediction?.signal && prediction.signal !== 'none') {
    pushViolation(
      violations,
      'no_ui_truth',
      'Predictive Runtime darf eine aktive Prediction nicht als erledigte Aktion darstellen.',
    );
  }

  if (input.actionEvent?.kind === 'done' && prediction?.signal && prediction.signal !== 'none') {
    pushViolation(
      violations,
      'no_gate_bypass',
      'Predictive Runtime darf kein Done-Event für eine nicht ausgeführte Runtime-Aktion erzeugen.',
    );
  }

  return {
    allowed: violations.length === 0,
    checkedPolicies: CHECKED_POLICIES,
    violations,
  };
}

export function assertPredictiveRuntimePolicy(input: PredictiveRuntimePolicyInput): void {
  const result = evaluatePredictiveRuntimePolicy(input);
  if (!result.allowed) {
    throw new Error(result.violations.map((violation) => `${violation.code}: ${violation.message}`).join('\n'));
  }
}
