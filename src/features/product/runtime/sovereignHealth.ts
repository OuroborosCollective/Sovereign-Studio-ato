import type { RepoFile } from '../../github/types';
import { analyzeRepoFileIntegrityList } from './repoFileIntegrity';
import type { GeneratedFileReviewReport } from './generatedFileReview';
import type { WorkflowWatchReport } from './workflowWatch';
import type { SovereignTelemetryEvent, SovereignTelemetryState } from './sovereignTelemetry';

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

let latestSovereignHealthReport: SovereignHealthReport | null = null;

export function getLatestSovereignHealthReport(): SovereignHealthReport | null {
  return latestSovereignHealthReport;
}

export function clearLatestSovereignHealthReportForTests(): void {
  latestSovereignHealthReport = null;
}

function rememberLatestSovereignHealthReport(report: SovereignHealthReport): SovereignHealthReport {
  latestSovereignHealthReport = report;
  return report;
}

function isDependencyTelemetry(event: SovereignTelemetryEvent): boolean {
  return event.label.startsWith('dependency:');
}

function isDependencyWaiting(event: SovereignTelemetryEvent): boolean {
  return isDependencyTelemetry(event) && (
    event.label.endsWith(':idle') ||
    event.label.endsWith(':checking') ||
    event.label.endsWith(':recovering')
  );
}

function normalizeHealthText(value: string): string {
  return value.toLowerCase().replace(/\s+/g, ' ').trim();
}

export function isHealthGateFeedbackTelemetry(event: SovereignTelemetryEvent): boolean {
  const label = normalizeHealthText(event.label);
  const message = normalizeHealthText(event.message);
  const combined = `${label} ${message}`;

  if (message.includes('health red prevents guarded output')) return true;
  if (message.includes('health idle prevents guarded output')) return true;
  if (message.includes('health gate blockiert')) return true;
  if (message.includes('runtime needs attention') && message.includes('health')) return true;

  const healthGateFailure = (
    label === 'sequence:draft-pr-publish:failed' ||
    label === 'guards:failed' ||
    label.includes('health')
  ) && (
    message.startsWith('health red:') ||
    message.startsWith('health idle:') ||
    message.includes('prevents guarded output') ||
    message.includes('health gate')
  );

  return healthGateFailure || combined.includes('health gate blockiert');
}

export function buildSovereignHealthReport(input: SovereignHealthInput): SovereignHealthReport {
  const telemetryEvents = Array.isArray(input.telemetry?.events) ? input.telemetry.events : [];
  const dependencyEvents = telemetryEvents.filter(isDependencyTelemetry);
  const nonDependencyEvents = telemetryEvents.filter((event) => !isDependencyTelemetry(event));
  const scoringTelemetryEvents = nonDependencyEvents.filter((event) => !isHealthGateFeedbackTelemetry(event));

  const integrity = analyzeRepoFileIntegrityList(input.repoFiles);
  const highIntegrity = integrity.filter((item) => item.riskLevel === 'high').length;
  const mediumIntegrity = integrity.filter((item) => item.riskLevel === 'medium').length;
  const highGenerated = input.generatedFileReview?.highRiskCount ?? 0;
  const workflowRed = input.workflowWatch?.status === 'red' ? 1 : 0;
  const workflowPending = input.workflowWatch?.status === 'pending' ? 1 : 0;
  const telemetryErrors = scoringTelemetryEvents.filter((event) => event.level === 'error').length;
  const dependencyErrors = dependencyEvents.filter((event) => event.level === 'error').length;
  const dependencyWarnings = dependencyEvents.filter((event) => event.level === 'warning').length;
  const dependencyWaiting = dependencyEvents.filter(isDependencyWaiting).length;

  // Existing repository path findings are advisory. Real repositories often contain
  // build/, dist/, Android assets, archives, or legacy paths. Those paths must be
  // shown for review, but they must not block planning/package generation before
  // the generated output is known. Red remains reserved for active runtime blockers:
  // unsafe generated output, failed workflows, and real telemetry/dependency errors.
  // Health-gate feedback events are intentionally excluded from scoring; otherwise
  // a blocked publish attempt logs an error, which turns health red again and creates
  // the fast self-amplifying loop visible in Android WebView.
  const criticalRisks = highGenerated + workflowRed + telemetryErrors + dependencyErrors;
  const totalIssues = criticalRisks + highIntegrity + mediumIntegrity + workflowPending + dependencyWarnings + dependencyWaiting;
  const repairsLogged = telemetryEvents.filter((event) => event.label.includes('draft-pr-created') || event.label.includes('guards:passed')).length;
  const branchDelta = criticalRisks > 0
    ? 1
    : workflowPending > 0 || dependencyWarnings > 0 || dependencyWaiting > 0 || highIntegrity > 0 || mediumIntegrity > 0
      ? 0.5
      : input.workflowWatch?.status === 'green'
        ? -1
        : 0;

  const recommendations: string[] = [];
  if (!input.repoFiles.length) recommendations.push('Load a real repository snapshot before judging health.');
  if (highIntegrity > 0) recommendations.push('Review high-risk repository paths before publishing changes; existing repo paths do not block planning.');
  if (mediumIntegrity > 0) recommendations.push('Review medium-risk repository paths for accuracy and completeness.');
  if (highGenerated > 0) recommendations.push('Generated file review found high-risk output and should block publishing.');
  if (workflowRed > 0) recommendations.push('Inspect failed workflow checks and prepare a focused repair package.');
  if (workflowPending > 0) recommendations.push('Wait for pending workflow checks before creating follow-up repairs.');
  if (dependencyErrors > 0) recommendations.push('Open Telemetry and resolve blocked dependency signals before continuing.');
  if (dependencyWarnings > 0) recommendations.push('Review degraded dependency signals before publishing or repairing.');
  if (dependencyWaiting > 0) recommendations.push('Initialize waiting dependency checks before judging readiness.');
  if (telemetryErrors > 0) recommendations.push('Open Telemetry and resolve the latest error event first.');
  if (!recommendations.length) recommendations.push('No blocking health issue detected from the available local signals.');

  const status: SovereignHealthStatus = !input.repoFiles.length
    ? 'idle'
    : criticalRisks > 0
      ? 'red'
      : totalIssues > 0
        ? 'warning'
        : 'green';

  return rememberLatestSovereignHealthReport({
    status,
    criticalRisks,
    totalIssues,
    repairsLogged,
    branchDelta,
    recommendations,
    summary: `Health ${status}: ${criticalRisks} critical risk(s), ${totalIssues} total issue(s), ${repairsLogged} repair signal(s).`,
  });
}
