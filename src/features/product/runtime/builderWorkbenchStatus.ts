/**
 * Sovereign Builder Workbench status slots.
 *
 * Translates internal runtime module signals (INT/ROU/PAT/SYN/ORC/LOG/BUD) into
 * user-understandable Workbench status truth: Actions, Files, Logs, Errors, Draft PR.
 *
 * Hard rule: this module only reads existing runtime state (logs, worker blocker,
 * OpenHands job, repo error, published PR). It never invents log lines, files or
 * actions. Empty slots stay empty and are labelled as such by the caller.
 *
 * Issue #504: Error deduplication - same blocker should not be counted multiple times.
 */
import type { WorkerRuntimeBlocker } from './builderContainerTypes';
import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';
import { deriveBlockerNextAction } from './sovereignBlockerRegistry';
import type { GitHubAccessState } from './githubAccessRuntime';

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
  readonly workerBlocker: WorkerRuntimeBlocker | null;
  readonly chatRepoError: string | null;
  readonly openhandsJob?: OpenHandsJobSnapshot;
  readonly publishedPrUrl?: string;
  /** GitHub access state for Issue #504 */
  readonly githubState?: GitHubAccessState;
  /** OpenHands configured state for Issue #504 */
  readonly openhandsConfigured?: boolean;
  /** Patch route available for Issue #504 */
  readonly patchRouteAvailable?: boolean;
}

const TAB_NAVIGATION_PREFIX = 'Tab → ';

function isTabNavigationLog(msg: string): boolean {
  return msg.startsWith(TAB_NAVIGATION_PREFIX);
}

function isSignalLog(level: string): boolean {
  return level === 'signal';
}

function isNoiseLevel(level: string): boolean {
  return level === 'error' || level === 'warn';
}

function isResolvedGithubAccessLog(input: WorkbenchStatusInput, msg: string): boolean {
  if (input.githubState !== 'ready') return false;
  const lower = msg.toLowerCase();
  return lower.includes('github write access missing')
    || lower.includes('github-zugang erforderlich')
    || lower.includes('github-schreibzugang fehlt')
    || lower.includes('write intent blocked: github write access missing')
    || lower.includes('github access missing');
}

/** System Actions: real started/executed actions, excluding tab navigation and raw signal noise. */
export function deriveSystemActionEntries(input: WorkbenchStatusInput): string[] {
  return input.logs
    .filter((log) => !isTabNavigationLog(log.msg) && !isSignalLog(log.level) && !isNoiseLevel(log.level))
    .map((log) => `${log.ts} · ${log.msg}`);
}

/** Edited Files: only real OpenHands changed files, never invented paths. */
export function deriveEditedFileEntries(input: WorkbenchStatusInput): string[] {
  return [...(input.openhandsJob?.changedFiles ?? [])];
}

/** Logs: full chronological runtime log, human readable. */
export function deriveLogEntries(input: WorkbenchStatusInput): string[] {
  return input.logs.map((log) => `${log.ts} · [${log.level}] ${log.msg}`);
}

/** Errors: worker blocker, repo load failure, failed/blocked OpenHands job and log-level errors/warnings.
 * Issue #504: Deduplicates by normalized message to prevent repeated blockers from inflating count.
 */
export function deriveErrorEntries(input: WorkbenchStatusInput): string[] {
  const entries: string[] = [];
  const seenMessages = new Set<string>();

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
  if (input.openhandsJob?.status === 'failed') {
    addUniqueEntry(`Sovereign Agent Job fehlgeschlagen${input.openhandsJob.lastError ? ` · ${input.openhandsJob.lastError}` : ''}`);
  }
  if (input.openhandsJob?.status === 'blocked') {
    addUniqueEntry(`Sovereign Agent Job blockiert${input.openhandsJob.lastError ? ` · ${input.openhandsJob.lastError}` : ''}`);
  }
  for (const log of input.logs) {
    if (isNoiseLevel(log.level) && !isResolvedGithubAccessLog(input, log.msg)) {
      addUniqueEntry(`${log.ts} · ${log.msg}`);
    }
  }
  return entries;
}

export function deriveDraftPrUrl(input: WorkbenchStatusInput): string | undefined {
  return input.openhandsJob?.draftPrUrl ?? input.publishedPrUrl;
}

export function deriveDraftPrStatus(input: WorkbenchStatusInput): { label: string; tone: WorkbenchStatusTone } {
  if (deriveDraftPrUrl(input)) return { label: 'bereit', tone: 'positive' };
  if (input.openhandsJob?.status === 'running' || input.openhandsJob?.status === 'queued') {
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
  if (input.githubState !== undefined || input.openhandsConfigured !== undefined) {
    return deriveBlockerNextAction({
      githubReady: input.githubState === 'ready',
      githubValidating: input.githubState === 'validating',
      executorAvailable: input.openhandsJob?.status === 'running' || input.openhandsJob?.status === 'queued',
      patchRouteAvailable: input.patchRouteAvailable ?? false,
      openhandsConfigured: input.openhandsConfigured ?? false,
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
