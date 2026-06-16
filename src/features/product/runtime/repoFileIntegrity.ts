import type { RepoFile } from '../../github/types';

export type IntegrityRiskLevel = 'low' | 'medium' | 'high';
export type IntegrityConfidence = 'path-only' | 'metadata';

export interface RepoFileIntegrityResult {
  path: string;
  fileName: string;
  type: RepoFile['type'];
  size?: number;
  riskLevel: IntegrityRiskLevel;
  confidence: IntegrityConfidence;
  score: number;
  flags: string[];
  reason: string;
}

const HIGH_RISK_PATTERNS = [
  /(^|\/)\.env(\.|$)/i,
  /(^|\/)secrets?(\.|\/|$)/i,
  /(^|\/)credentials?(\.|\/|$)/i,
  /(^|\/)private[-_]?key/i,
  /(^|\/)node_modules\//i,
  /(^|\/)dist\//i,
  /(^|\/)build\//i,
];

const MEDIUM_RISK_PATTERNS = [
  /todo/i,
  /mock/i,
  /stub/i,
  /fixture/i,
  /sample/i,
  /\.bak$/i,
  /\.old$/i,
];

const CODE_EXTENSIONS = ['.ts', '.tsx', '.js', '.jsx', '.kt', '.java', '.py', '.go', '.rs', '.mjs', '.cjs'];
const TEST_PATTERNS = [/\.test\./i, /\.spec\./i, /(^|\/)tests?\//i, /(^|\/)__tests__\//i];

function fileNameOf(path: string): string {
  return path.split('/').filter(Boolean).at(-1) ?? path;
}

function isCodePath(path: string): boolean {
  const lower = path.toLowerCase();
  return CODE_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function hasPattern(path: string, patterns: RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(path));
}

function clampScore(score: number): number {
  return Math.max(0, Math.min(100, Math.round(score)));
}

export function analyzeRepoFileIntegrity(file: RepoFile): RepoFileIntegrityResult {
  const path = file.path;
  const lower = path.toLowerCase();
  const flags: string[] = [];
  let score = 80;

  if (file.type === 'tree') {
    return {
      path,
      fileName: fileNameOf(path),
      type: file.type,
      size: file.size,
      riskLevel: 'low',
      confidence: 'path-only',
      score: 70,
      flags: ['folder'],
      reason: 'Folder entry only. File content was not inspected.',
    };
  }

  if (isCodePath(lower)) {
    score += 10;
    flags.push('code');
  }

  if (TEST_PATTERNS.some((pattern) => pattern.test(path))) {
    score += 5;
    flags.push('test');
  }

  if (hasPattern(path, HIGH_RISK_PATTERNS)) {
    score -= 55;
    flags.push('high-risk-path');
  }

  if (hasPattern(path, MEDIUM_RISK_PATTERNS)) {
    score -= 20;
    flags.push('review-keyword');
  }

  if ((file.size ?? 0) > 500_000) {
    score -= 15;
    flags.push('large-file');
  }

  const finalScore = clampScore(score);
  const riskLevel: IntegrityRiskLevel = finalScore < 45 ? 'high' : finalScore < 70 ? 'medium' : 'low';
  const reason = flags.length
    ? `Path-only checks: ${flags.join(', ')}.`
    : 'Path-only checks found no obvious risk markers.';

  return {
    path,
    fileName: fileNameOf(path),
    type: file.type,
    size: file.size,
    riskLevel,
    confidence: 'path-only',
    score: finalScore,
    flags,
    reason,
  };
}

export function analyzeRepoFileIntegrityList(files: RepoFile[]): RepoFileIntegrityResult[] {
  return files.map(analyzeRepoFileIntegrity).sort((a, b) => {
    const riskOrder: Record<IntegrityRiskLevel, number> = { high: 0, medium: 1, low: 2 };
    return riskOrder[a.riskLevel] - riskOrder[b.riskLevel] || a.path.localeCompare(b.path);
  });
}

export function summarizeFileIntegrity(results: RepoFileIntegrityResult[]): string {
  const high = results.filter((item) => item.riskLevel === 'high').length;
  const medium = results.filter((item) => item.riskLevel === 'medium').length;
  const low = results.filter((item) => item.riskLevel === 'low').length;
  return `${results.length} entries analyzed (${high} high, ${medium} medium, ${low} low). Confidence: path-only.`;
}
