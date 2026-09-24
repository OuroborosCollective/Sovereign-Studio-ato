import type { DependencyImpact } from './dependencyImpactRuntime';

export interface MergeBlastRadiusInput {
  readonly changedPaths: readonly string[];
  readonly totalAddedLines: number;
  readonly totalRemovedLines: number;
  readonly dependencyImpact?: readonly DependencyImpact[];
  readonly testEvidenceReady?: boolean;
  readonly securityEvidenceReady?: boolean;
  readonly releaseEvidenceReady?: boolean;
}

export interface MergeBlastRadiusResult {
  readonly score: number;
  readonly level: 'low' | 'medium' | 'high' | 'critical';
  readonly reasons: readonly string[];
  readonly requiresAdditionalEvidence: boolean;
}

// ⚡ Bolt: Hoist regular expression to module scope to prevent re-compiling inside array filter loops.
const CRITICAL_PATH_REGEX = /(^|\/)(auth|billing|security|migrations?|workflows?|deploy|runtime)(\/|\.|$)/i;

/**
 * ⚡ Bolt: Consolidated single-pass merge blast radius gate evaluation.
 * Avoids multi-pass array allocations (.filter, Set, [...Set], .reduce, .some)
 * by deduplicating paths, categorizing critical surfaces, and summing importer impact in a single pass.
 */
export function buildMergeBlastRadiusGate(input: MergeBlastRadiusInput): MergeBlastRadiusResult {
  const seenPaths = new Set<string>();
  const uniquePaths: string[] = [];
  const criticalPaths: string[] = [];

  for (const path of input.changedPaths) {
    if (path && !seenPaths.has(path)) {
      seenPaths.add(path);
      uniquePaths.push(path);
      if (CRITICAL_PATH_REGEX.test(path)) {
        criticalPaths.push(path);
      }
    }
  }

  const changedLines = Math.max(0, input.totalAddedLines) + Math.max(0, input.totalRemovedLines);

  let importerCount = 0;
  if (input.dependencyImpact) {
    for (const entry of input.dependencyImpact) {
      importerCount += entry.importerCount;
    }
  }

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
  const evidenceMissing = input.testEvidenceReady === false || input.securityEvidenceReady === false || input.releaseEvidenceReady === false;
  const requiresAdditionalEvidence = (level === 'high' || level === 'critical') && evidenceMissing;
  if (requiresAdditionalEvidence) reasons.push('High blast radius requires complete test, security, and release evidence.');

  return { score, level, reasons, requiresAdditionalEvidence };
}
