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
  summary: string;
}

const HIGH_RISK_PATHS = [/^\.env/i, /^\.git\//i, /^node_modules\//i, /^dist\//i, /^build\//i];
const MEDIUM_RISK_PATHS = [/\.ya?ml$/i, /workflow/i, /package\.json$/i, /vite\.config/i, /tsconfig/i];
const SECRET_MARKERS = [/api[_-]?key/i, /token/i, /secret/i, /password/i, /private[_-]?key/i];

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

  return {
    files: reviewed,
    totalFiles: reviewed.length,
    totalLines,
    totalChars,
    highRiskCount,
    mediumRiskCount,
    summary: `${reviewed.length} generated file(s), ${totalLines} line(s), ${highRiskCount} high risk, ${mediumRiskCount} medium risk.`,
  };
}

export function assertGeneratedFileReviewSafe(report: GeneratedFileReviewReport): void {
  if (report.totalFiles === 0) throw new Error('No generated files to review.');
  if (report.highRiskCount > 0) throw new Error(`Generated file review found ${report.highRiskCount} high-risk file(s).`);
}
