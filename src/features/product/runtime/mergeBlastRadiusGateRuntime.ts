import type { DependencyImpactEntry } from './dependencyImpactRuntime';

export interface MergeBlastRadiusInput {
  changedPaths: readonly string[];
  totalAddedLines: number;
  totalRemovedLines: number;
  dependencyImpact?: readonly DependencyImpactEntry[];
  testEvidenceReady?: boolean;
  securityEvidenceReady?: boolean;
  releaseEvidenceReady?: boolean;
}

export interface MergeBlastRadiusResult {
  score: number;
  level: 'low' | 'medium' | 'high' | 'critical';
  reasons: string[];
  requiresAdditionalEvidence: boolean;
}

export function buildMergeBlastRadiusGate(input: MergeBlastRadiusInput): MergeBlastRadiusResult {
  const uniquePaths = [...new Set(input.changedPaths.filter(Boolean))];
  const changedLines = Math.max(0, input.totalAddedLines) + Math.max(0, input.totalRemovedLines);
  const importerCount = (input.dependencyImpact ?? []).reduce((sum, entry) => sum + entry.importerCount, 0);
  const criticalPaths = uniquePaths.filter((path) => /(^|\/)(auth|billing|security|migrations?|workflows?|deploy|runtime)(\/|\.|$)/i.test(path));
  const reasons: string[] = [];
  let score = 0;

  score += Math.min(25, uniquePaths.length * 2);
  score += Math.min(25, Math.floor(changedLines / 40));
  score += Math.min(25, importerCount * 2);
  score += Math.min(25, criticalPaths.length * 8);

  if (uniquePaths.length > 10) reasons.push(`${uniquePaths.length} files are changed.`);
  if (changedLines > 400) reasons.push(`${changedLines} changed lines increase review surface.`);
  if (importerCount > 10) reasons.push(`${importerCount} importer edges are affected.`);
  if (criticalPaths.length) reasons.push(`Critical surfaces changed: ${criticalPaths.join(', ')}.`);

  const level = score >= 75 ? 'critical' : score >= 50 ? 'high' : score >= 25 ? 'medium' : 'low';
  const evidenceMissing = [input.testEvidenceReady, input.securityEvidenceReady, input.releaseEvidenceReady]
    .some((value) => value === false);
  const requiresAdditionalEvidence = (level === 'high' || level === 'critical') && evidenceMissing;
  if (requiresAdditionalEvidence) reasons.push('High blast radius requires complete test, security, and release evidence.');

  return { score, level, reasons, requiresAdditionalEvidence };
}
