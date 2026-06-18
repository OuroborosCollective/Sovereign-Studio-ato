import type { ImplementationFile } from './sovereignRuntime';

export type GeneratedFileReviewRisk = 'low' | 'medium' | 'high';

export interface GeneratedFileReviewItem {
  path: string;
  reason: string;
  lineCount: number;
  charCount: number;
  risk: GeneratedFileReviewRisk;
  flags: string[];
  preview: string;
}

export interface GeneratedFileReviewReport {
  files: GeneratedFileReviewItem[];
  totalFiles: number;
  totalLines: number;
  totalChars: number;
  highRiskCount: number;
  mediumRiskCount: number;
  planOnlyCount: number;
  actionableFileCount: number;
  summary: string;
}

const HIGH_RISK_PATHS = [/^\.env/i, /^\.git\//i, /^node_modules\//i, /^dist\//i, /^build\//i];
const MEDIUM_RISK_PATHS = [/\.ya?ml$/i, /workflow/i, /package\.json$/i, /vite\.config/i, /tsconfig/i];
const SECRET_MARKERS = [/api[_-]?key/i, /token/i, /secret/i, /password/i, /private[_-]?key/i];
const PLAN_ONLY_PATHS = new Set(['docs/sovereign_plan.md', 'generated/sovereign-product/workflow.ts']);
const ACTIONABLE_PATHS = [/^src\//i, /^tests?\//i, /\.test\.[tj]sx?$/i, /\.spec\.[tj]sx?$/i, /^android\//i, /^scripts\//i, /^\.github\//i, /^package\.json$/i, /^vite\.config/i, /^tsconfig/i];

function normalizePath(path: string): string {
  return path.trim().replace(/^\/+/, '');
}

function lineCount(content: string): number {
  if (!content) return 0;
  return content.split(/\r?\n/).length;
}

function previewOf(content: string, maxChars = 1200): string {
  return content.length > maxChars ? `${content.slice(0, maxChars)}\n…` : content;
}

function isPlanOnlyPath(path: string): boolean {
  return PLAN_ONLY_PATHS.has(path.toLowerCase());
}

function isActionablePath(path: string): boolean {
  return ACTIONABLE_PATHS.some((pattern) => pattern.test(path));
}

export function reviewGeneratedFile(file: ImplementationFile): GeneratedFileReviewItem {
  const path = normalizePath(file.path);
  const flags: string[] = [];
  let risk: GeneratedFileReviewRisk = 'low';

  if (HIGH_RISK_PATHS.some((pattern) => pattern.test(path))) {
    flags.push('forbidden-looking-path');
    risk = 'high';
  }

  if (SECRET_MARKERS.some((pattern) => pattern.test(file.content))) {
    flags.push('secret-marker-in-content');
    risk = 'high';
  }

  if (MEDIUM_RISK_PATHS.some((pattern) => pattern.test(path))) {
    flags.push('workflow-or-config');
    if (risk === 'low') risk = 'medium';
  }

  if (isPlanOnlyPath(path)) {
    flags.push('plan-only-output');
    if (risk === 'low') risk = 'medium';
  }

  if (isActionablePath(path)) {
    flags.push('actionable-output');
  }

  if (file.content.length > 25_000) {
    flags.push('large-generated-file');
    if (risk === 'low') risk = 'medium';
  }

  if (!file.content.trim()) {
    flags.push('empty-content');
    risk = 'high';
  }

  return {
    path,
    reason: file.reason,
    lineCount: lineCount(file.content),
    charCount: file.content.length,
    risk,
    flags,
    preview: previewOf(file.content),
  };
}

export function reviewGeneratedFiles(files: ImplementationFile[]): GeneratedFileReviewReport {
  const reviewed = files.map(reviewGeneratedFile);
  const totalLines = reviewed.reduce((sum, file) => sum + file.lineCount, 0);
  const totalChars = reviewed.reduce((sum, file) => sum + file.charCount, 0);
  const highRiskCount = reviewed.filter((file) => file.risk === 'high').length;
  const mediumRiskCount = reviewed.filter((file) => file.risk === 'medium').length;
  const planOnlyCount = reviewed.filter((file) => file.flags.includes('plan-only-output')).length;
  const actionableFileCount = reviewed.filter((file) => file.flags.includes('actionable-output')).length;

  return {
    files: reviewed,
    totalFiles: reviewed.length,
    totalLines,
    totalChars,
    highRiskCount,
    mediumRiskCount,
    planOnlyCount,
    actionableFileCount,
    summary: `${reviewed.length} generated file(s), ${totalLines} line(s), ${highRiskCount} high risk, ${mediumRiskCount} medium risk, ${actionableFileCount} actionable.`,
  };
}

export function assertGeneratedFileReviewSafe(report: GeneratedFileReviewReport): void {
  if (report.totalFiles === 0) throw new Error('No generated files to review.');
  if (report.highRiskCount > 0) throw new Error(`Generated file review found ${report.highRiskCount} high-risk file(s).`);
  if (report.planOnlyCount > 0 && report.actionableFileCount === 0) {
    throw new Error('Self review rejected plan-only output. Rewrite required: change real source, runtime, test, workflow, Android, or script files before Draft PR.');
  }
}
