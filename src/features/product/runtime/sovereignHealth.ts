import type { RepoFile } from '../../github/types';
import { analyzeRepoFileIntegrityList } from './repoFileIntegrity';
import type { GeneratedFileReviewReport } from './generatedFileReview';
import type { WorkflowWatchReport } from './workflowWatch';
import type { SovereignTelemetryState } from './sovereignTelemetry';

export type SovereignHealthStatus = 'green' | 'warning' | 'red' | 'idle';

export interface SovereignHealthReport {
  status: SovereignHealthStatus;
  criticalRisks: number;
  totalIssues: number;
  repairsLogged: number;
  branchDelta: number;
  summary: string;
  recommendations: string[];
}

export interface SovereignHealthInput {
  repoFiles: RepoFile[];
  generatedFileReview?: GeneratedFileReviewReport | null;
  workflowWatch?: WorkflowWatchReport | null;
  telemetry?: SovereignTelemetryState | null;
}

export function buildSovereignHealthReport(input: SovereignHealthInput): SovereignHealthReport {
  const integrity = analyzeRepoFileIntegrityList(input.repoFiles);
  const highIntegrity = integrity.filter((item) => item.riskLevel === 'high').length;
  const mediumIntegrity = integrity.filter((item) => item.riskLevel === 'medium').length;
  const highGenerated = input.generatedFileReview?.highRiskCount ?? 0;
  const mediumGenerated = input.generatedFileReview?.mediumRiskCount ?? 0;
  const workflowRed = input.workflowWatch?.status === 'red' ? 1 : 0;
  const workflowPending = input.workflowWatch?.status === 'pending' ? 1 : 0;
  const telemetryErrors = input.telemetry?.events.filter((event) => event.level === 'error').length ?? 0;

  const criticalRisks = highIntegrity + highGenerated + workflowRed + telemetryErrors;
  const totalIssues = criticalRisks + mediumIntegrity + workflowPending;
  const repairsLogged = input.telemetry?.events.filter((event) => event.label.includes('draft-pr-created') || event.label.includes('guards:passed')).length ?? 0;
  const branchDelta = workflowRed > 0 ? 1 : workflowPending > 0 ? 0.5 : input.workflowWatch?.status === 'green' ? -1 : 0;

  const recommendations: string[] = [];
  if (!input.repoFiles.length) recommendations.push('Load a real repository snapshot before judging health.');
  if (highIntegrity > 0) recommendations.push('Review high-risk repository paths before publishing changes.');
  if (mediumIntegrity > 0) recommendations.push('Review medium-risk repository paths for accuracy and completeness.');
  if (highGenerated > 0) recommendations.push('Generated file review found high-risk output and should block publishing.');
  if (workflowRed > 0) recommendations.push('Inspect failed workflow checks and prepare a focused repair package.');
  if (workflowPending > 0) recommendations.push('Wait for pending workflow checks before creating follow-up repairs.');
  if (telemetryErrors > 0) recommendations.push('Open Telemetry and resolve the latest error event first.');
  if (!recommendations.length) recommendations.push('No blocking health issue detected from the available local signals.');

  const status: SovereignHealthStatus = !input.repoFiles.length
    ? 'idle'
    : criticalRisks > 0
      ? 'red'
      : totalIssues > 0
        ? 'warning'
        : 'green';

  return {
    status,
    criticalRisks,
    totalIssues,
    repairsLogged,
    branchDelta,
    recommendations,
    summary: `Health ${status}: ${criticalRisks} critical risk(s), ${totalIssues} total issue(s), ${repairsLogged} repair signal(s).`,
  };
}
