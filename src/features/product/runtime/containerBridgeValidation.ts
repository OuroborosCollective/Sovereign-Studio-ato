/**
 * Container Bridge Validation
 * Runtime-Checks für alle wichtigen Übergaben zwischen Containern
 */

import type { RepoFile } from '../../github/types';
import type { GeneratedFileReviewReport } from './generatedFileReview';
import type { WorkflowWatchReport } from './workflowWatch';

export type BridgeValidationSeverity = 'error' | 'warning' | 'info';

export interface BridgeValidationResult {
  valid: boolean;
  severity: BridgeValidationSeverity;
  message: string;
  details: string[];
}

export interface RepoToBuilderBridge {
  repoReady: boolean;
  fileCount: number;
  repoUrl: string;
  branch: string;
  tokenInLogs: boolean;
}

export interface BuilderToGeneratedFilesBridge {
  mission: string;
  isPlaceholder: boolean;
  repoSnapshotReady: boolean;
  packageHasFiles: boolean;
  filesActionable: boolean;
  planOnlyOnly: boolean;
}

export interface GeneratedFilesToDiffBridge {
  packageExists: boolean;
  pathsValid: boolean;
  sourcesLoaded: boolean;
  isNewFile: boolean;
}

export interface FilesToDraftPRBridge {
  selfReviewAccepted: boolean;
  actionableOutput: boolean;
  planOnlyOnly: boolean;
  tokenPresent: boolean;
  repoParsed: boolean;
  branchNonceSafe: boolean;
  secretsInLogs: boolean;
}

export interface WorkflowToFindingsBridge {
  commitSha: string | null;
  workflowResultValid: boolean;
  redStatus: boolean;
  greenStatus: boolean;
  staleResult: boolean;
}

export interface RemoteMemoryToPatternMemoryBridge {
  gatewayConfigValid: boolean;
  contributorId: string | null;
  collectionName: string | null;
  workspaceId: string | null;
  deleteConfirmationsComplete: boolean;
  sharedPatternDetected: boolean;
}

export interface TelemetryToCoachBridge {
  eventValid: boolean;
  noSecrets: boolean;
  stagesKnown: string[];
  latestByStageConsistent: boolean;
  noisyEventsCount: number;
}

// Helper functions
function isValidUrl(url: string): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

function isValidBranch(branch: string): boolean {
  if (!branch) return false;
  // Basic branch validation - not empty, no dangerous chars
  return /^[a-zA-Z0-9_/-]+$/.test(branch) && branch.length <= 255;
}

function containsSecrets(text: string): boolean {
  const secretPatterns = [
    /token/i,
    /secret/i,
    /password/i,
    /api[_-]?key/i,
    /ghp_[a-zA-Z0-9]{36}/,
    /gho_[a-zA-Z0-9]{36}/,
    /private[_-]?key/i,
  ];
  return secretPatterns.some((pattern) => pattern.test(text));
}

// Repo → Builder Bridge
export function validateRepoToBuilderBridge(bridge: RepoToBuilderBridge): BridgeValidationResult {
  const details: string[] = [];

  if (!bridge.repoReady) {
    details.push('Repo not ready - snapshot not loaded');
  }

  if (bridge.fileCount === 0) {
    details.push('No files in repository snapshot');
  }

  if (!isValidUrl(bridge.repoUrl)) {
    details.push('Invalid repository URL');
  }

  if (!isValidBranch(bridge.branch)) {
    details.push('Invalid or missing branch');
  }

  if (bridge.tokenInLogs) {
    details.push('WARNING: Token may be in logs');
  }

  const valid = bridge.repoReady && bridge.fileCount > 0 && isValidUrl(bridge.repoUrl);
  const hasWarning = details.some((d) => d.includes('WARNING'));
  const severity: BridgeValidationSeverity = valid && !hasWarning ? 'info' : hasWarning ? 'warning' : 'error';
  return {
    valid,
    severity,
    message: valid
      ? 'Repo → Builder bridge valid'
      : 'Repo → Builder bridge has issues',
    details,
  };
}

// Builder → Generated Files Bridge
export function validateBuilderToGeneratedFilesBridge(bridge: BuilderToGeneratedFilesBridge): BridgeValidationResult {
  const details: string[] = [];

  if (!bridge.mission || !bridge.mission.trim()) {
    details.push('Mission is empty');
  }

  if (bridge.isPlaceholder) {
    details.push('WARNING: Mission is a placeholder');
  }

  if (!bridge.repoSnapshotReady) {
    details.push('Repository snapshot not ready');
  }

  if (!bridge.packageHasFiles) {
    details.push('Generated package has no files');
  }

  if (!bridge.filesActionable) {
    details.push('Files are not actionable');
  }

  if (bridge.planOnlyOnly) {
    details.push('WARNING: Plan-only mode - no actual file generation');
  }

  const hasMission = Boolean(bridge.mission && bridge.mission.trim());
  const valid = hasMission && !bridge.isPlaceholder && bridge.repoSnapshotReady && bridge.packageHasFiles && bridge.filesActionable;
  const severity: BridgeValidationSeverity = valid && bridge.planOnlyOnly ? 'warning' : valid ? 'info' : details.some((d) => d.startsWith('WARNING')) ? 'warning' : 'error';
  return {
    valid,
    severity,
    message: valid
      ? 'Builder → Generated Files bridge valid'
      : 'Builder → Generated Files bridge has issues',
    details,
  };
}

// Generated Files → Diff Bridge
export function validateGeneratedFilesToDiffBridge(bridge: GeneratedFilesToDiffBridge): BridgeValidationResult {
  const details: string[] = [];

  if (!bridge.packageExists) {
    details.push('Package does not exist');
  }

  if (!bridge.pathsValid) {
    details.push('Paths are not valid');
  }

  if (!bridge.sourcesLoaded) {
    details.push('Source files not loaded - missing sources marked');
  }

  if (bridge.isNewFile) {
    details.push('INFO: New file detected - not an error');
  }

  const valid = bridge.packageExists && bridge.pathsValid;
  return {
    valid,
    severity: valid ? 'info' : 'error',
    message: valid
      ? 'Generated Files → Diff bridge valid'
      : 'Generated Files → Diff bridge has issues',
    details,
  };
}

// Generated Files/Diff → Draft PR Bridge
export function validateFilesToDraftPRBridge(bridge: FilesToDraftPRBridge): BridgeValidationResult {
  const details: string[] = [];

  if (!bridge.selfReviewAccepted) {
    details.push('Self-review not accepted');
  }

  if (!bridge.actionableOutput) {
    details.push('No actionable output');
  }

  if (bridge.planOnlyOnly) {
    details.push('WARNING: Plan-only mode - no real changes');
  }

  if (!bridge.tokenPresent) {
    details.push('Token not present - required for private repos');
  }

  if (!bridge.repoParsed) {
    details.push('Repository not parsed');
  }

  if (!bridge.branchNonceSafe) {
    details.push('WARNING: Branch nonce may not be safe');
  }

  if (bridge.secretsInLogs) {
    details.push('ERROR: Secrets detected in logs');
  }

  const valid = bridge.selfReviewAccepted && bridge.actionableOutput && !bridge.planOnlyOnly && bridge.tokenPresent && bridge.repoParsed && !bridge.secretsInLogs;
  return {
    valid,
    severity: bridge.secretsInLogs ? 'error' : details.some((d) => d.startsWith('ERROR')) ? 'error' : details.some((d) => d.startsWith('WARNING')) ? 'warning' : 'info',
    message: valid
      ? 'Files → Draft PR bridge valid'
      : 'Files → Draft PR bridge has issues',
    details,
  };
}

// Workflow → Findings/Repair Bridge
export function validateWorkflowToFindingsBridge(bridge: WorkflowToFindingsBridge): BridgeValidationResult {
  const details: string[] = [];

  if (!bridge.commitSha) {
    details.push('Commit SHA not available');
  }

  if (!bridge.workflowResultValid) {
    details.push('Workflow result not valid');
  }

  if (bridge.staleResult) {
    details.push('WARNING: Workflow result is stale');
  }

  if (bridge.redStatus) {
    details.push('Workflow status RED - repair plan should be generated');
  }

  if (bridge.greenStatus) {
    details.push('Workflow status GREEN - review guidance available');
  }

  const valid = Boolean(bridge.commitSha) && bridge.workflowResultValid;
  const severity = bridge.redStatus ? 'warning' : bridge.staleResult ? 'warning' : valid ? 'info' : 'error';
  return {
    valid,
    severity,
    message: valid
      ? 'Workflow → Findings bridge valid'
      : 'Workflow → Findings bridge has issues',
    details,
  };
}

// Remote Memory → Pattern Memory Bridge
export function validateRemoteMemoryToPatternMemoryBridge(bridge: RemoteMemoryToPatternMemoryBridge): BridgeValidationResult {
  const details: string[] = [];

  if (!bridge.gatewayConfigValid) {
    details.push('Gateway config not valid');
  }

  if (!bridge.contributorId) {
    details.push('Contributor ID not available');
  }

  if (!bridge.collectionName) {
    details.push('Collection name not available');
  }

  if (!bridge.workspaceId) {
    details.push('Workspace ID not available');
  }

  if (!bridge.deleteConfirmationsComplete) {
    details.push('Delete confirmations not complete');
  }

  if (bridge.sharedPatternDetected) {
    details.push('WARNING: Shared pattern detected - do not delete');
  }

  const valid = bridge.gatewayConfigValid && bridge.contributorId && bridge.collectionName && bridge.workspaceId && bridge.deleteConfirmationsComplete;
  return {
    valid,
    severity: bridge.sharedPatternDetected ? 'warning' : valid ? 'info' : 'error',
    message: valid
      ? 'Remote Memory → Pattern Memory bridge valid'
      : 'Remote Memory → Pattern Memory bridge has issues',
    details,
  };
}

// Telemetry → Coach/Workbench Bridge
export function validateTelemetryToCoachBridge(bridge: TelemetryToCoachBridge): BridgeValidationResult {
  const details: string[] = [];

  if (!bridge.eventValid) {
    details.push('Event not valid');
  }

  if (!bridge.noSecrets) {
    details.push('ERROR: Secrets detected in telemetry');
  }

  if (!bridge.stagesKnown || bridge.stagesKnown.length === 0) {
    details.push('No known stages');
  }

  if (!bridge.latestByStageConsistent) {
    details.push('WARNING: latestByStage inconsistent');
  }

  if (bridge.noisyEventsCount > 10) {
    details.push(`WARNING: ${bridge.noisyEventsCount} noisy events - consider consolidation`);
  }

  const valid = bridge.eventValid && bridge.noSecrets && bridge.stagesKnown.length > 0;
  return {
    valid,
    severity: !bridge.noSecrets ? 'error' : details.some((d) => d.startsWith('ERROR')) ? 'error' : details.some((d) => d.startsWith('WARNING')) ? 'warning' : 'info',
    message: valid
      ? 'Telemetry → Coach bridge valid'
      : 'Telemetry → Coach bridge has issues',
    details,
  };
}

// Composite validation for full pipeline
export interface FullPipelineBridge {
  repoToBuilder: RepoToBuilderBridge;
  builderToGeneratedFiles: BuilderToGeneratedFilesBridge;
  generatedFilesToDiff: GeneratedFilesToDiffBridge;
  filesToDraftPR: FilesToDraftPRBridge;
  workflowToFindings: WorkflowToFindingsBridge;
  remoteMemoryToPatternMemory: RemoteMemoryToPatternMemoryBridge;
  telemetryToCoach: TelemetryToCoachBridge;
}

export function validateFullPipeline(bridge: FullPipelineBridge): {
  overallValid: boolean;
  results: BridgeValidationResult[];
  criticalErrors: string[];
} {
  const results = [
    validateRepoToBuilderBridge(bridge.repoToBuilder),
    validateBuilderToGeneratedFilesBridge(bridge.builderToGeneratedFiles),
    validateGeneratedFilesToDiffBridge(bridge.generatedFilesToDiff),
    validateFilesToDraftPRBridge(bridge.filesToDraftPR),
    validateWorkflowToFindingsBridge(bridge.workflowToFindings),
    validateRemoteMemoryToPatternMemoryBridge(bridge.remoteMemoryToPatternMemory),
    validateTelemetryToCoachBridge(bridge.telemetryToCoach),
  ];

  const criticalErrors = results
    .filter((r) => r.severity === 'error')
    .flatMap((r) => r.details);

  const overallValid = results.every((r) => r.valid || r.severity !== 'error');

  return { overallValid, results, criticalErrors };
}