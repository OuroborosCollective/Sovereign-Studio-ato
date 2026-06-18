export type SovereignAutomationMode = 'manual' | 'auto-review' | 'full-auto-draft-pr';

export interface SovereignAutomationInputs {
  mode: SovereignAutomationMode;
  repoReady: boolean;
  hasMission: boolean;
  hasToken: boolean;
  isBusy: boolean;
  hasPackage: boolean;
  lastAutoRunKey?: string;
  nextAutoRunKey: string;
}

export interface SovereignAutomationDecision {
  shouldBuildPackage: boolean;
  shouldPublishDraftPr: boolean;
  blockedReason?: string;
}

export const AUTOMATION_MODE_LABELS: Record<SovereignAutomationMode, string> = {
  manual: 'Manual',
  'auto-review': 'Auto Review',
  'full-auto-draft-pr': 'Full Auto Draft PR',
};

const PLACEHOLDER_MISSION_TOKEN = '|README + Update History|';

export function describeAutomationMode(mode: SovereignAutomationMode): string {
  if (mode === 'manual') return 'Manual mode: user clicks each action.';
  if (mode === 'auto-review') return 'Auto Review: build and review generated files after a valid repo snapshot exists.';
  return 'Full Auto Draft PR: build, review and create a guarded Draft PR when repo, mission and PAT are available.';
}

export function buildAutomationRunKey(input: {
  mode: SovereignAutomationMode;
  repoUrl: string;
  repoBranch: string;
  mission: string;
  repoFileCount: number;
  previewHash?: string;
}): string {
  return [
    input.mode,
    input.repoUrl.trim(),
    input.repoBranch.trim(),
    input.mission.trim(),
    String(input.repoFileCount),
    input.previewHash ?? '',
  ].join('|');
}

export function isPlaceholderAutomationRunKey(value: string): boolean {
  return value.includes(PLACEHOLDER_MISSION_TOKEN);
}

export function decideSovereignAutomation(input: SovereignAutomationInputs): SovereignAutomationDecision {
  if (input.mode === 'manual') return { shouldBuildPackage: false, shouldPublishDraftPr: false };
  if (input.isBusy) return { shouldBuildPackage: false, shouldPublishDraftPr: false, blockedReason: 'Automation is waiting for the current action to finish.' };
  if (!input.repoReady) return { shouldBuildPackage: false, shouldPublishDraftPr: false, blockedReason: 'Automation needs a loaded repository snapshot.' };
  if (!input.hasMission) return { shouldBuildPackage: false, shouldPublishDraftPr: false, blockedReason: 'Automation needs a concrete mission.' };
  if (isPlaceholderAutomationRunKey(input.nextAutoRunKey)) {
    return { shouldBuildPackage: false, shouldPublishDraftPr: false, blockedReason: 'Automation wartet auf einen konkreten Auftrag. README + Update History ist nur ein Platzhalter.' };
  }
  if (input.lastAutoRunKey && input.lastAutoRunKey === input.nextAutoRunKey) {
    return { shouldBuildPackage: false, shouldPublishDraftPr: false, blockedReason: 'Automation already handled this exact input snapshot.' };
  }

  if (input.mode === 'auto-review') {
    return { shouldBuildPackage: true, shouldPublishDraftPr: false };
  }

  if (!input.hasToken) {
    return { shouldBuildPackage: false, shouldPublishDraftPr: false, blockedReason: 'Full Auto Draft PR needs a GitHub PAT.' };
  }

  return {
    shouldBuildPackage: !input.hasPackage,
    shouldPublishDraftPr: true,
  };
}

export function isFullAutoMode(mode: SovereignAutomationMode): boolean {
  return mode === 'full-auto-draft-pr';
}
