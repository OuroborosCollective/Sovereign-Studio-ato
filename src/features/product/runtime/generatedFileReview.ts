import type { ImplementationFile } from './sovereignRuntime';
import { scanForSecret } from './secureInputGuard';

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

export interface GeneratedFileSelfReview {
  accepted: boolean;
  rewriteRequired: boolean;
  reason: string;
  learningSignal: string;
  rewritePlan: string[];
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
  selfReview: GeneratedFileSelfReview;
  summary: string;
}

const HIGH_RISK_PATHS = [/^\.env/i, /^\.git\//i, /^node_modules\//i, /^dist\//i, /^build\//i];
const MEDIUM_RISK_PATHS = [/\.ya?ml$/i, /workflow/i, /package\.json$/i, /vite\.config/i, /tsconfig/i];
const PLAN_ONLY_PATHS = new Set(['docs/sovereign_plan.md', 'generated/sovereign-product/workflow.ts']);
const ACTIONABLE_PATHS = [/^src\//i, /^tests?\//i, /\.test\.[tj]sx?$/i, /\.spec\.[tj]sx?$/i, /^android\//i, /^scripts\//i, /^\.github\//i, /^package\.json$/i, /^vite\.config/i, /^tsconfig/i, /^readme\.md$/i, /^docs\//i];

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

function buildSelfReview(args: { totalFiles: number; highRiskCount: number; planOnlyCount: number; actionableFileCount: number }): GeneratedFileSelfReview {
  if (args.totalFiles === 0) {
    return {
      accepted: false,
      rewriteRequired: true,
      reason: 'No generated files were produced.',
      learningSignal: 'empty-output-rejected',
      rewritePlan: ['Generate real implementation files before presenting work.', 'Include at least one source, runtime, test, workflow, Android, or script file.'],
    };
  }

  if (args.highRiskCount > 0) {
    return {
      accepted: false,
      rewriteRequired: true,
      reason: `${args.highRiskCount} high-risk generated file(s) detected.`,
      learningSignal: 'high-risk-output-rejected',
      rewritePlan: ['Remove forbidden paths and sensitive-looking content.', 'Regenerate a minimal safe implementation package.', 'Run review again before Draft PR.'],
    };
  }

  if (args.planOnlyCount > 0 && args.actionableFileCount === 0) {
    return {
      accepted: false,
      rewriteRequired: true,
      reason: 'Generated package only contains plan/audit artifacts and no actionable implementation file.',
      learningSignal: 'plan-only-output-rejected',
      rewritePlan: ['Reflect on the requested user outcome.', 'Select real affected source/runtime/test/workflow files.', 'Rewrite the package so at least one actionable file changes.', 'Keep any plan file only as support, never as the sole result.'],
    };
  }

  return {
    accepted: true,
    rewriteRequired: false,
    reason: 'Generated package passed self review.',
    learningSignal: 'generated-output-accepted',
    rewritePlan: [],
  };
}

export function reviewGeneratedFile(file: ImplementationFile): GeneratedFileReviewItem {
  const path = normalizePath(file.path);
  const flags: string[] = [];
  let risk: GeneratedFileReviewRisk = 'low';

  if (HIGH_RISK_PATHS.some((pattern) => pattern.test(path))) {
    flags.push('forbidden-looking-path');
    risk = 'high';
  }

  if (scanForSecret(file.content).detected) {
    flags.push('secret-value-in-content');
    risk = 'high';
  }

  if (MEDIUM_RISK_PATHS.some((pattern) => pattern.test(path))) {
    flags.push('workflow-or-config');
    if (risk === 'low') risk = 'medium';
  }

  if (isPlanOnlyPath(path)) {
    flags.push('plan-only-output');
    if (risk === 'low') risk = 'medium';
  } else if (isActionablePath(path)) {
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
  const selfReview = buildSelfReview({ totalFiles: reviewed.length, highRiskCount, planOnlyCount, actionableFileCount });

  return {
    files: reviewed,
    totalFiles: reviewed.length,
    totalLines,
    totalChars,
    highRiskCount,
    mediumRiskCount,
    planOnlyCount,
    actionableFileCount,
    selfReview,
    summary: `${reviewed.length} generated file(s), ${totalLines} line(s), ${highRiskCount} high risk, ${mediumRiskCount} medium risk, ${actionableFileCount} actionable. Self review: ${selfReview.learningSignal}.`,
  };
}

export function assertGeneratedFileReviewSafe(report: GeneratedFileReviewReport): void {
  if (report.totalFiles === 0) throw new Error('No generated files to review.');
  if (report.highRiskCount > 0) throw new Error(`Generated file review found ${report.highRiskCount} high-risk file(s).`);
  if (report.selfReview.rewriteRequired) {
    throw new Error(`Self review rejected generated output: ${report.selfReview.reason} Rewrite plan: ${report.selfReview.rewritePlan.join(' | ')}`);
  }
}
