/**
 * Sovereign Builder Workbench status slots.
 *
 * Translates internal runtime module signals (INT/ROU/PAT/SYN/ORC/LOG/BUD) into
 * user-understandable Workbench status truth: Actions, Files, Logs, Errors, Draft PR.
 *
 * Hard rule: this module only reads existing runtime state (logs, worker blocker,
 * Sovereign Agent job, repo error, published PR). It never invents log lines, files or
 * actions. Empty slots stay empty and are labelled as such by the caller.
 *
 * Issue #504: Error deduplication - same blocker should not be counted multiple times.
 */
import type { WorkerRuntimeBlocker } from './builderContainerTypes';
import type { SovereignAgentJobSnapshot } from './sovereignAgentRuntime';
import { deriveBlockerNextAction } from './sovereignBlockerRegistry';
import type { GitHubAccessState } from './githubAccessRuntime';
import type { SovereignActionEvent, SovereignActionKind } from './sovereignActionStreamRuntime';

export type WorkbenchStatusSlotId = 'actions' | 'files' | 'logs' | 'errors' | 'draftPr';
export type WorkbenchStatusTone = 'neutral' | 'positive' | 'warning' | 'error';

export interface WorkbenchStatusLogEntry {
  readonly ts: string;
  readonly level: string;
  readonly msg: string;
  readonly tabId: string;
}

export interface WorkbenchStatusSlot {
  readonly id: WorkbenchStatusSlotId;
  readonly label: string;
  readonly value: string;
  readonly tone: WorkbenchStatusTone;
  readonly items: readonly string[];
  readonly emptyLabel: string;
  /** Issue #504: Next action based on actual runtime state */
  readonly nextAction?: string;
}

/** Extended input for Issue #504 honest status display */
export interface WorkbenchStatusInput {
  readonly logs: readonly WorkbenchStatusLogEntry[];
  readonly actionEvents?: readonly SovereignActionEvent[];
  readonly workerBlocker: WorkerRuntimeBlocker | null;
  readonly chatRepoError: string | null;
  readonly agentJob?: SovereignAgentJobSnapshot;
  readonly publishedPrUrl?: string;
  /** GitHub access state for Issue #504 */
  readonly githubState?: GitHubAccessState;
  /** Sovereign Agent configured state for Issue #504 */
  readonly agentConfigured?: boolean;
  /** Patch route available for Issue #504 */
  readonly patchRouteAvailable?: boolean;
}

const WORKBENCH_OPERATIONAL_ACTION_KINDS: ReadonlySet<SovereignActionKind> = new Set([
  'repo_context_loaded',
  'llm_request_started',
  'patch_generated',
  'patch_validating',
  'executor_started',
  'draft_pr_ready',
  'agent_job_requested',
  'agent_job_created',
  'agent_workspace_provisioning',
  'agent_workspace_ready',
  'agent_tool_started',
  'agent_tool_finished',
  'agent_diff_ready',
  'agent_tests_finished',
  'agent_result_validating',
  'agent_result_ready',
  'agent_workspace_cleanup_started',
  'agent_workspace_cleaned',
]);

function actionEntry(event: SovereignActionEvent): string {
  return event.detail?.trim() ? `${event.label} · ${event.detail.trim()}` : event.label;
}

/**
 * System Actions are projected only from explicitly operational Action-Stream kinds.
 * Input, intent, route selection, context collection, answers, diagnostics and generic
 * status events remain evidence/logs and never inflate the action counter.
 */
export function deriveSystemActionEntries(input: WorkbenchStatusInput): string[] {
  return (input.actionEvents ?? [])
    .filter((event) =>
      WORKBENCH_OPERATIONAL_ACTION_KINDS.has(event.kind)
      && event.state !== 'blocked'
      && event.state !== 'failed'
    )
    .map(actionEntry);
}

/** Edited Files: only real Sovereign Agent changed files, never invented paths. */
export function deriveEditedFileEntries(input: WorkbenchStatusInput): string[] {
  return [...(input.agentJob?.changedFiles ?? [])];
}

/** Logs: full chronological runtime log, human readable. */
export function deriveLogEntries(input: WorkbenchStatusInput): string[] {
  return input.logs.map((log) => `${log.ts} · [${log.level}] ${log.msg}`);
}

/**
 * Errors: current canonical blockers, failed/blocked Agent state and structured
 * failed Action-Stream events. Text logs remain exclusively in Logs so one runtime
 * failure cannot inflate Errors through a second mirrored log line.
 */
export function deriveErrorEntries(input: WorkbenchStatusInput): string[] {
  const entries: string[] = [];
  const seenMessages = new Set<string>();
  const seenActionFailures = new Set<string>();

  function addUniqueEntry(msg: string) {
    // Normalize for deduplication: lowercase, remove timestamps, collapse whitespace
    const normalized = msg.toLowerCase().replace(/^\d+:\d+:\d+\s*/, '').replace(/\s+/g, ' ').trim();
    if (!seenMessages.has(normalized)) {
      seenMessages.add(normalized);
      entries.push(msg);
    }
  }

  if (input.workerBlocker) {
    addUniqueEntry(`Worker blockiert · ${input.workerBlocker.message}`);
  }
  if (input.chatRepoError) {
    addUniqueEntry(`Repo Ladefehler · ${input.chatRepoError}`);
  }
  if (input.agentJob?.status === 'failed') {
    addUniqueEntry(`Sovereign Agent Job fehlgeschlagen${input.agentJob.lastError ? ` · ${input.agentJob.lastError}` : ''}`);
  }
  if (input.agentJob?.status === 'blocked') {
    addUniqueEntry(`Sovereign Agent Job blockiert${input.agentJob.lastError ? ` · ${input.agentJob.lastError}` : ''}`);
  }
  for (const event of input.actionEvents ?? []) {
    if (event.state !== 'failed') continue;
    if (event.route === 'worker' && input.workerBlocker) continue;
    if (event.route === 'repo' && input.chatRepoError) continue;
    if (event.route === 'agent-job' && input.agentJob?.status === 'failed') continue;
    const key = [event.route, event.kind, event.sourceId ?? '', event.target ?? '', event.label].join(':');
    if (seenActionFailures.has(key)) continue;
    seenActionFailures.add(key);
    addUniqueEntry(actionEntry(event));
  }
  return entries;
}

export function deriveDraftPrUrl(input: WorkbenchStatusInput): string | undefined {
  return input.agentJob?.draftPrUrl ?? input.publishedPrUrl;
}

export function deriveDraftPrStatus(input: WorkbenchStatusInput): { label: string; tone: WorkbenchStatusTone } {
  if (deriveDraftPrUrl(input)) return { label: 'bereit', tone: 'positive' };
  if (input.agentJob?.status === 'running' || input.agentJob?.status === 'queued') {
    return { label: 'läuft', tone: 'warning' };
  }
  return { label: 'fehlt', tone: 'neutral' };
}

/**
 * Derive honest next action based on Issue #504 rules.
 * Uses blocker registry logic to determine correct next step.
 */
function deriveHonestNextAction(input: WorkbenchStatusInput): string {
  // If extended inputs are provided, use blocker registry logic
  if (input.githubState !== undefined || input.agentConfigured !== undefined) {
    return deriveBlockerNextAction({
      githubReady: input.githubState === 'ready',
      githubValidating: input.githubState === 'validating',
      executorAvailable: input.agentJob?.status === 'running' || input.agentJob?.status === 'queued',
      patchRouteAvailable: input.patchRouteAvailable ?? false,
      agentConfigured: input.agentConfigured ?? false,
    });
  }

  // Default: no specific action
  return '';
}

export function deriveWorkbenchStatusSlots(input: WorkbenchStatusInput): WorkbenchStatusSlot[] {
  const actions = deriveSystemActionEntries(input);
  const files = deriveEditedFileEntries(input);
  const logs = deriveLogEntries(input);
  const errors = deriveErrorEntries(input);
  const draftPr = deriveDraftPrStatus(input);
  const draftPrUrl = deriveDraftPrUrl(input);
  const nextAction = deriveHonestNextAction(input);

  return [
    {
      id: 'actions',
      label: 'Actions',
      value: String(actions.length),
      tone: 'neutral',
      items: actions,
      emptyLabel: 'Noch keine Actions',
    },
    {
      id: 'files',
      label: 'Changed',
      value: String(files.length),
      tone: 'neutral',
      items: files,
      emptyLabel: 'Noch keine Änderungen',
    },
    {
      id: 'logs',
      label: 'Logs',
      value: String(logs.length),
      tone: 'neutral',
      items: logs,
      emptyLabel: 'Noch keine Logs',
    },
    {
      id: 'errors',
      label: 'Errors',
      value: String(errors.length),
      tone: errors.length > 0 ? 'error' : 'neutral',
      items: errors,
      emptyLabel: 'Keine Fehler',
      nextAction: errors.length > 0 ? nextAction : undefined,
    },
    {
      id: 'draftPr',
      label: 'Draft PR',
      value: draftPr.label,
      tone: draftPr.tone,
      items: draftPrUrl ? [draftPrUrl] : [],
      emptyLabel: 'Noch kein Draft PR',
    },
  ];
}

/** Legacy function for backwards compatibility */
export function deriveWorkbenchStatusSlotsLegacy(input: WorkbenchStatusInput): WorkbenchStatusSlot[] {
  const actions = deriveSystemActionEntries(input);
  const files = deriveEditedFileEntries(input);
  const logs = deriveLogEntries(input);
  const errors = deriveErrorEntries(input);
  const draftPr = deriveDraftPrStatus(input);
  const draftPrUrl = deriveDraftPrUrl(input);

  return [
    {
      id: 'actions',
      label: 'Actions',
      value: String(actions.length),
      tone: 'neutral',
      items: actions,
      emptyLabel: 'Noch keine Actions',
    },
    {
      id: 'files',
      label: 'Changed',
      value: String(files.length),
      tone: 'neutral',
      items: files,
      emptyLabel: 'Noch keine Änderungen',
    },
    {
      id: 'logs',
      label: 'Logs',
      value: String(logs.length),
      tone: 'neutral',
      items: logs,
      emptyLabel: 'Noch keine Logs',
    },
    {
      id: 'errors',
      label: 'Errors',
      value: String(errors.length),
      tone: errors.length > 0 ? 'error' : 'neutral',
      items: errors,
      emptyLabel: 'Keine Fehler',
    },
    {
      id: 'draftPr',
      label: 'Draft PR',
      value: draftPr.label,
      tone: draftPr.tone,
      items: draftPrUrl ? [draftPrUrl] : [],
      emptyLabel: 'Noch kein Draft PR',
    },
  ];
}
