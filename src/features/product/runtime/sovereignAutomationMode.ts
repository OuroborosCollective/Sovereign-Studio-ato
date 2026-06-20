import { getLatestSovereignHealthReport } from './sovereignHealth';
import { getSovereignHealthRuntimeGate } from './sovereignFunctionalGuards';

export type SovereignAutomationMode = 'manual' | 'auto-review' | 'full-auto-draft-pr';
export type SovereignAutomationHealthStatus = 'green' | 'warning' | 'red' | 'idle';

export interface SovereignAutomationInputs {
  mode: SovereignAutomationMode;
  repoReady: boolean;
  hasMission: boolean;
  hasToken: boolean;
  isBusy: boolean;
  hasPackage: boolean;
  lastAutoRunKey?: string;
  nextAutoRunKey: string;
  healthAllowed?: boolean;
  healthStatus?: SovereignAutomationHealthStatus;
  healthReason?: string;
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

/**
 * Build a comprehensive automation run key
 * 
 * The key includes:
 * - automationMode
 * - repoUrl
 * - repoBranch
 * - githubTokenPresent
 * - repoSnapshotStatus.ready
 * - repoFiles.length
 * - mission.trim()
 * - solutionPatternStore.version or updatedAt
 * - last blocking error hash
 */
export function buildAutomationRunKey(input: {
  mode: SovereignAutomationMode;
  repoUrl: string;
  repoBranch: string;
  githubTokenPresent?: boolean;
  repoReady?: boolean;
  mission: string;
  repoFileCount: number;
  solutionPatternVersion?: string | null;
  lastBlockingErrorHash?: string | null;
  previewHash?: string;
  healthStatus?: SovereignAutomationHealthStatus;
}): string {
  const parts = [
    // Mode
    input.mode,
    // Repo identity
    input.repoUrl.trim() || 'none',
    input.repoBranch.trim() || 'main',
    // Token presence (never the actual token)
    input.githubTokenPresent ? 'has-token' : 'no-token',
    // Repo ready state
    input.repoReady ? 'ready' : 'not-ready',
    // Health state
    input.healthStatus ?? 'health-unknown',
    // File count
    String(input.repoFileCount),
    // Mission
    input.mission.trim() || 'no-mission',
    // Pattern memory version
    input.solutionPatternVersion || 'no-patterns',
    // Last blocking error hash
    input.lastBlockingErrorHash || 'no-error',
    // Preview hash if present
    input.previewHash ?? '',
  ];
  
  return parts.join('|');
}

export function isPlaceholderAutomationRunKey(value: string): boolean {
  return value.includes(PLACEHOLDER_MISSION_TOKEN);
}

function resolveHealthGate(input: SovereignAutomationInputs): {
  allowed: boolean;
  status?: SovereignAutomationHealthStatus;
  reason?: string;
} | null {
  if (input.healthAllowed !== undefined) {
    return {
      allowed: input.healthAllowed,
      status: input.healthStatus,
      reason: input.healthReason,
    };
  }

  const latestReport = getLatestSovereignHealthReport();
  if (!latestReport) return null;
  const gate = getSovereignHealthRuntimeGate(latestReport);
  return {
    allowed: gate.allowed,
    status: gate.status,
    reason: gate.reason,
  };
}

function healthBlocksAutomation(input: SovereignAutomationInputs): string | null {
  const gate = resolveHealthGate(input);
  if (!gate || gate.allowed) return null;
  if (gate.status === 'red' || gate.status === 'idle' || gate.status === undefined) {
    return gate.reason || `Automation blocked by ${gate.status ?? 'unknown'} runtime readiness.`;
  }
  return null;
}

export function decideSovereignAutomation(input: SovereignAutomationInputs): SovereignAutomationDecision {
  if (input.mode === 'manual') return { shouldBuildPackage: false, shouldPublishDraftPr: false };
  if (input.isBusy) return { shouldBuildPackage: false, shouldPublishDraftPr: false, blockedReason: 'Automation is waiting for the current action to finish.' };
  if (!input.repoReady) return { shouldBuildPackage: false, shouldPublishDraftPr: false, blockedReason: 'Automation needs a loaded repository snapshot.' };
  const healthBlockedReason = healthBlocksAutomation(input);
  if (healthBlockedReason) {
    return {
      shouldBuildPackage: false,
      shouldPublishDraftPr: false,
      blockedReason: healthBlockedReason,
    };
  }
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
