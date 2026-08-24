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
  // Performance optimization: Replace `content.split(/\r?\n/).length` with an O(N) character scan
  // for '\n' (charCodeAt 10) to avoid allocating large string arrays in memory.
  let count = 1;
  for (let i = 0; i < content.length; i++) {
    if (content.charCodeAt(i) === 10) count++;
  }
  return count;
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
  // Performance optimization: Consolidate review generated files, line/char summations,
  // and risk/flag counts into a single-pass O(N) loop to eliminate redundant array allocations
  // and 6 sequential .map(), .reduce(), and .filter() passes.
  const reviewed: GeneratedFileReviewItem[] = new Array(files.length);
  let totalLines = 0;
  let totalChars = 0;
  let highRiskCount = 0;
  let mediumRiskCount = 0;
  let planOnlyCount = 0;
  let actionableFileCount = 0;

  for (let i = 0; i < files.length; i++) {
    const item = reviewGeneratedFile(files[i]);
    reviewed[i] = item;
    totalLines += item.lineCount;
    totalChars += item.charCount;

    if (item.risk === 'high') {
      highRiskCount++;
    } else if (item.risk === 'medium') {
      mediumRiskCount++;
    }

    if (item.flags.includes('plan-only-output')) {
      planOnlyCount++;
    }
    if (item.flags.includes('actionable-output')) {
      actionableFileCount++;
    }
  }

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
