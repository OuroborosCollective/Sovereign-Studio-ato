import {
  buildBrownfieldReport,
  type BrownfieldReport,
  type BrownfieldSeverity,
} from './brownfieldExplorer';

export type BrownfieldInspectorLamp = 'green' | 'yellow' | 'red';

export interface BrownfieldInspectorInput {
  repoName: string;
  branch: string;
  files: Array<string | { path: string }>;
  analyzedAt?: number;
}

export interface BrownfieldInspectorHint {
  visible: boolean;
  lamp: BrownfieldInspectorLamp;
  label: string;
  message: string;
  detail: string;
  targetTab: 'findings' | 'health';
  report: BrownfieldReport;
}

function pathFromEntry(entry: string | { path: string }): string {
  return typeof entry === 'string' ? entry : entry.path;
}

function mostSevereFinding(report: BrownfieldReport): BrownfieldSeverity | null {
  if (report.findings.some((finding) => finding.severity === 'critical')) return 'critical';
  if (report.findings.some((finding) => finding.severity === 'warn')) return 'warn';
  if (report.findings.some((finding) => finding.severity === 'info')) return 'info';
  return null;
}

function lampFor(report: BrownfieldReport): BrownfieldInspectorLamp {
  const severity = mostSevereFinding(report);
  if (severity === 'critical') return 'red';
  if (severity === 'warn') return 'yellow';
  return 'green';
}

function targetTabFor(report: BrownfieldReport): 'findings' | 'health' {
  return mostSevereFinding(report) === 'critical' ? 'health' : 'findings';
}

function messageFor(report: BrownfieldReport): string {
  if (report.fileCount === 0) return 'Noch kein Repo-Baum geladen.';
  const critical = report.findings.filter((finding) => finding.severity === 'critical').length;
  const warnings = report.findings.filter((finding) => finding.severity === 'warn').length;
  if (critical > 0) return `Brownfield: ${critical} kritische Struktur-Signale gefunden.`;
  if (warnings > 0) return `Brownfield: ${warnings} prüfenswerte Repo-Signale gefunden.`;
  return 'Brownfield: Repo-Struktur wirkt stabil.';
}

function detailFor(report: BrownfieldReport): string {
  const hotspots = report.topHotspots.slice(0, 3);
  if (hotspots.length === 0) return report.summary;
  return `${report.summary} · Hotspots: ${hotspots.join(', ')}`;
}

export function buildBrownfieldInspectorHint(input: BrownfieldInspectorInput): BrownfieldInspectorHint {
  const report = buildBrownfieldReport({
    repoName: input.repoName,
    branch: input.branch,
    files: input.files.map(pathFromEntry),
    analyzedAt: input.analyzedAt,
  });

  return {
    visible: report.fileCount > 0,
    lamp: lampFor(report),
    label: `Brownfield ${report.score.total}/100`,
    message: messageFor(report),
    detail: detailFor(report),
    targetTab: targetTabFor(report),
    report,
  };
}
