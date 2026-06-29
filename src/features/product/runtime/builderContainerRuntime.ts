export interface BuilderContainerRuntimeInput {
  repoReady: boolean;
  runtimeBusy: boolean;
  repoBusy: boolean;
  isPublishing: boolean;
  mission: string;
  sovereignSummary: string;
  sovereignPreview: string;
}

export interface BuilderContainerRuntimeState {
  canGenerate: boolean;
  canPublish: boolean;
  hasMission: boolean;
  hasSummary: boolean;
  hasPreview: boolean;
  disabledReason: string;
}

/** Workspace status for short German messages */
export type WorkspaceStatus = 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'blocked' | 'cleaned';

export interface WorkspaceRuntimeState {
  status: WorkspaceStatus;
  shortMessage: string;
  canShowInspector: boolean;
  inspectorUrl?: string;
}

export const BUILDER_PLACEHOLDER_MISSIONS = new Set([
  'README + Update History',
]);

export function normalizeBuilderMission(value: string): string {
  return value.replace(/\s+/g, ' ').trim().slice(0, 2000);
}

export function isPlaceholderMission(value: string): boolean {
  return BUILDER_PLACEHOLDER_MISSIONS.has(normalizeBuilderMission(value));
}

export function deriveBuilderContainerState(input: BuilderContainerRuntimeInput): BuilderContainerRuntimeState {
  const normalizedMission = normalizeBuilderMission(input.mission);
  const hasMission = normalizedMission.length > 0;
  const hasSummary = input.sovereignSummary.trim().length > 0;
  const hasPreview = input.sovereignPreview.trim().length > 0;

  if (!input.repoReady) {
    return { canGenerate: false, canPublish: false, hasMission, hasSummary, hasPreview, disabledReason: 'Repository snapshot is not ready.' };
  }
  if (input.repoBusy) {
    return { canGenerate: false, canPublish: false, hasMission, hasSummary, hasPreview, disabledReason: 'Repository is busy.' };
  }
  if (input.runtimeBusy) {
    return { canGenerate: false, canPublish: false, hasMission, hasSummary, hasPreview, disabledReason: 'Sequential runtime is busy.' };
  }
  if (input.isPublishing) {
    return { canGenerate: false, canPublish: false, hasMission, hasSummary, hasPreview, disabledReason: 'Draft PR publishing is running.' };
  }
  if (!hasMission) {
    return { canGenerate: false, canPublish: false, hasMission, hasSummary, hasPreview, disabledReason: 'Mission is empty.' };
  }
  if (isPlaceholderMission(normalizedMission)) {
    return { canGenerate: false, canPublish: false, hasMission, hasSummary, hasPreview, disabledReason: 'Bitte zuerst einen konkreten Auftrag analysieren. README + Update History ist nur ein Platzhalter.' };
  }

  return { canGenerate: true, canPublish: true, hasMission, hasSummary, hasPreview, disabledReason: '' };
}

export function builderPublishLabel(isPublishing: boolean): string {
  return isPublishing ? 'Draft PR läuft...' : 'Draft PR erstellen';
}

/**
 * Derive workspace runtime state from workspace result.
 * Produces short German messages for calm UI display.
 *
 * Rules from product law:
 * - Show short messages only
 * - Do not show raw terminal spam
 * - Do not show fake percentage progress
 * - Do not show green success without real result
 * - Inspector link only when URL is present and safe
 */
export function deriveWorkspaceRuntimeState(input: {
  status?: WorkspaceStatus;
  draftPrUrl?: string;
  blocker?: string;
  workspaceInspectorUrl?: string;
  changedFilesCount?: number;
}): WorkspaceRuntimeState {
  const { status = 'idle', draftPrUrl, blocker, workspaceInspectorUrl, changedFilesCount = 0 } = input;

  const isInspectorSafe = Boolean(
    workspaceInspectorUrl
    && workspaceInspectorUrl.startsWith('https://')
    && status !== 'blocked'
    && status !== 'cleaned',
  );

  let shortMessage: string;

  switch (status) {
    case 'idle':
      shortMessage = '';
      break;
    case 'queued':
      shortMessage = 'Workspace gestartet';
      break;
    case 'running':
      if (changedFilesCount > 0) {
        shortMessage = `Repo geklont · ${changedFilesCount} Datei(en)`;
      } else {
        shortMessage = 'Repo geklont · Tests laufen';
      }
      break;
    case 'completed':
      if (draftPrUrl) {
        shortMessage = 'Draft PR bereit';
      } else if (changedFilesCount > 0) {
        shortMessage = `${changedFilesCount} Änderung(en) fertig`;
      } else {
        shortMessage = 'Workspace abgeschlossen';
      }
      break;
    case 'failed':
      shortMessage = blocker ? `Blocker: ${truncate(blocker, 50)}` : 'Workspace fehlgeschlagen';
      break;
    case 'blocked':
      shortMessage = blocker ? `Blocker: ${truncate(blocker, 50)}` : 'Workspace blockiert';
      break;
    case 'cleaned':
      shortMessage = 'Workspace bereinigt';
      break;
    default:
      shortMessage = '';
  }

  return {
    status,
    shortMessage,
    canShowInspector: isInspectorSafe,
    inspectorUrl: isInspectorSafe ? workspaceInspectorUrl : undefined,
  };
}

function truncate(value: string, maxLength: number): string {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value;
}
