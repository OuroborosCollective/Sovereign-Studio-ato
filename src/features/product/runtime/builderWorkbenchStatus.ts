/**
 * Sovereign Builder Workbench status slots.
 *
 * Translates internal runtime module signals (INT/ROU/PAT/SYN/ORC/LOG/BUD) into
 * user-understandable Workbench status truth: Actions, Files, Logs, Errors, Draft PR.
 *
 * Hard rule: this module only reads existing runtime state (logs, worker blocker,
 * OpenHands job, repo error, published PR). It never invents log lines, files or
 * actions. Empty slots stay empty and are labelled as such by the caller.
 */
import type { WorkerRuntimeBlocker } from './builderContainerTypes';
import type { OpenHandsJobSnapshot } from './openhandsEnterpriseRuntime';

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
}

export interface WorkbenchStatusInput {
  readonly logs: readonly WorkbenchStatusLogEntry[];
  readonly workerBlocker: WorkerRuntimeBlocker | null;
  readonly chatRepoError: string | null;
  readonly openhandsJob?: OpenHandsJobSnapshot;
  readonly publishedPrUrl?: string;
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

/** Errors: worker blocker, repo load failure, failed/blocked OpenHands job and log-level errors/warnings. */
export function deriveErrorEntries(input: WorkbenchStatusInput): string[] {
  const entries: string[] = [];
  if (input.workerBlocker) {
    entries.push(`Worker blockiert · ${input.workerBlocker.message}`);
  }
  if (input.chatRepoError) {
    entries.push(`Repo Ladefehler · ${input.chatRepoError}`);
  }
  if (input.openhandsJob?.status === 'failed') {
    entries.push(`OpenHands Job fehlgeschlagen${input.openhandsJob.lastError ? ` · ${input.openhandsJob.lastError}` : ''}`);
  }
  if (input.openhandsJob?.status === 'blocked') {
    entries.push(`OpenHands Job blockiert${input.openhandsJob.lastError ? ` · ${input.openhandsJob.lastError}` : ''}`);
  }
  for (const log of input.logs) {
    if (isNoiseLevel(log.level)) {
      entries.push(`${log.ts} · ${log.msg}`);
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

export function deriveWorkbenchStatusSlots(input: WorkbenchStatusInput): WorkbenchStatusSlot[] {
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
      label: 'Files',
      value: String(files.length),
      tone: 'neutral',
      items: files,
      emptyLabel: 'Noch keine bearbeiteten Dateien',
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
