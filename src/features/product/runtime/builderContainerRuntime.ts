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

export function normalizeBuilderMission(value: string): string {
  return value.replace(/\s+/g, ' ').trim().slice(0, 2000);
}

export function deriveBuilderContainerState(input: BuilderContainerRuntimeInput): BuilderContainerRuntimeState {
  const hasMission = normalizeBuilderMission(input.mission).length > 0;
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

  return { canGenerate: true, canPublish: true, hasMission, hasSummary, hasPreview, disabledReason: '' };
}

export function builderPublishLabel(isPublishing: boolean): string {
  return isPublishing ? 'Draft PR läuft...' : 'Draft PR erstellen';
}
