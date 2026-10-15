/**
 * Sovereign Bolt.diy Snapshot Executor
 *
 * Deterministic handoff contract for remote coding environments that operate on
 * a repository ZIP instead of a persistent local workspace.
 *
 * This module does not call bolt.diy, GitHub, Blender, Python, or any production
 * service. It defines the exact revision/capability/evidence boundary that a
 * transport adapter must satisfy before Sovereign may treat a returned bundle as
 * execution evidence.
 */

import { normalizeWorkspacePath, sanitizeWorkspaceText } from './agentWorkspaceRuntime';

export const BOLT_SNAPSHOT_JOB_SCHEMA = 'sovereign.bolt-snapshot-job.v1' as const;
export const BOLT_SNAPSHOT_RESULT_SCHEMA = 'sovereign.bolt-snapshot-result.v1' as const;

export type BoltSnapshotCapability =
  | 'node'
  | 'terminal'
  | 'python'
  | 'blender-headless'
  | 'ninja'
  | 'gamedev-tools'
  | 'git-diff';

export type BoltSnapshotEvidenceKind =
  | 'snapshot-provenance'
  | 'diff'
  | 'tests'
  | 'build'
  | 'runtime-readback';

export interface BoltCapabilityObservation {
  readonly capability: BoltSnapshotCapability;
  readonly available: boolean;
  /**
   * Human-readable probe evidence, for example "Python 3.12.4" or
   * "Blender 4.3.2 background mode". The runtime never invents this value.
   */
  readonly evidence: string;
}

export interface BoltSnapshotSource {
  readonly repoFullName: string;
  readonly branch: string;
  readonly revision: string;
  readonly archiveFormat: 'zip';
}

export interface BoltSnapshotAuthority {
  readonly production: false;
  readonly rawVps: false;
  readonly rawDatabase: false;
  readonly gameplayMutation: false;
  readonly githubDirectMerge: false;
}

export interface BoltSnapshotJob {
  readonly schema: typeof BOLT_SNAPSHOT_JOB_SCHEMA;
  readonly executor: 'bolt-diy-snapshot';
  readonly source: BoltSnapshotSource;
  /**
   * Stable provenance key, not a cryptographic content hash.
   * The exact Git commit remains the source authority.
   */
  readonly snapshotKey: string;
  readonly expectedArchiveName: string;
  readonly observedCapabilities: readonly BoltSnapshotCapability[];
  readonly requiredEvidence: readonly BoltSnapshotEvidenceKind[];
  readonly authority: BoltSnapshotAuthority;
  readonly draftPrOnly: true;
}

export interface BoltSnapshotEvidence {
  readonly kind: BoltSnapshotEvidenceKind;
  readonly passed: boolean;
  readonly summary: string;
}

export interface BoltSnapshotResult {
  readonly schema: typeof BOLT_SNAPSHOT_RESULT_SCHEMA;
  readonly sourceRevision: string;
  readonly changedFiles: readonly string[];
  readonly evidence: readonly BoltSnapshotEvidence[];
}

export interface BoltSnapshotValidation {
  readonly allowed: boolean;
  readonly blockers: readonly string[];
  readonly warnings: readonly string[];
}

const REPO_FULL_NAME = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const SAFE_BRANCH = /^[\w./-]{1,160}$/;
const EXACT_GIT_SHA = /^[a-f0-9]{40}$/;

const DEFAULT_REQUIRED_EVIDENCE: readonly BoltSnapshotEvidenceKind[] = [
  'snapshot-provenance',
  'diff',
  'tests',
];

function uniqueSorted<T extends string>(values: readonly T[]): T[] {
  return [...new Set(values)].sort() as T[];
}

function safeEvidenceSummary(value: string): string {
  return sanitizeWorkspaceText(value.trim()).slice(0, 1200);
}

export function validateBoltSnapshotSource(source: BoltSnapshotSource): BoltSnapshotValidation {
  const blockers: string[] = [];

  if (!REPO_FULL_NAME.test(source.repoFullName.trim())) {
    blockers.push('Bolt snapshot requires repository identity in owner/name form.');
  }
  if (!SAFE_BRANCH.test(source.branch.trim())) {
    blockers.push('Bolt snapshot branch contains unsafe characters.');
  }
  if (!EXACT_GIT_SHA.test(source.revision.trim())) {
    blockers.push('Bolt snapshot must be pinned to an exact 40-character lowercase Git revision.');
  }
  if (source.archiveFormat !== 'zip') {
    blockers.push('Bolt snapshot transport only accepts ZIP archives.');
  }

  return {
    allowed: blockers.length === 0,
    blockers: uniqueSorted(blockers),
    warnings: [],
  };
}

export function resolveObservedBoltCapabilities(
  observations: readonly BoltCapabilityObservation[],
): readonly BoltSnapshotCapability[] {
  const available: BoltSnapshotCapability[] = [];

  for (const observation of observations) {
    if (!observation.available) continue;
    if (!observation.evidence.trim()) continue;
    available.push(observation.capability);
  }

  return uniqueSorted(available);
}

export function buildBoltSnapshotJob(input: {
  readonly repoFullName: string;
  readonly branch?: string;
  readonly revision: string;
  readonly observations?: readonly BoltCapabilityObservation[];
  readonly requiredEvidence?: readonly BoltSnapshotEvidenceKind[];
}): BoltSnapshotJob {
  const source: BoltSnapshotSource = {
    repoFullName: input.repoFullName.trim(),
    branch: input.branch?.trim() || 'main',
    revision: input.revision.trim(),
    archiveFormat: 'zip',
  };

  const sourceValidation = validateBoltSnapshotSource(source);
  if (!sourceValidation.allowed) {
    throw new Error(sourceValidation.blockers.join(' '));
  }

  const archiveSlug = source.repoFullName.replace('/', '-').replace(/[^A-Za-z0-9_.-]/g, '-');
  const observedCapabilities = resolveObservedBoltCapabilities(input.observations ?? []);
  const requiredEvidence = uniqueSorted(input.requiredEvidence?.length
    ? input.requiredEvidence
    : DEFAULT_REQUIRED_EVIDENCE);

  return {
    schema: BOLT_SNAPSHOT_JOB_SCHEMA,
    executor: 'bolt-diy-snapshot',
    source,
    snapshotKey: `${source.repoFullName}@${source.revision}`,
    expectedArchiveName: `${archiveSlug}-${source.revision.slice(0, 12)}.zip`,
    observedCapabilities,
    requiredEvidence,
    authority: {
      production: false,
      rawVps: false,
      rawDatabase: false,
      gameplayMutation: false,
      githubDirectMerge: false,
    },
    draftPrOnly: true,
  };
}

export function validateBoltSnapshotResult(
  job: BoltSnapshotJob,
  result: BoltSnapshotResult,
): BoltSnapshotValidation {
  const blockers: string[] = [];
  const warnings: string[] = [];

  if (result.schema !== BOLT_SNAPSHOT_RESULT_SCHEMA) {
    blockers.push('Bolt result schema is unsupported.');
  }
  if (result.sourceRevision !== job.source.revision) {
    blockers.push('Bolt result revision does not match the requested snapshot revision.');
  }

  const normalizedFiles: string[] = [];
  for (const path of result.changedFiles) {
    const normalized = normalizeWorkspacePath(path);
    if (!normalized) {
      blockers.push('Bolt result contains an unsafe changed-file path.');
      continue;
    }
    normalizedFiles.push(normalized);
  }

  if (normalizedFiles.length === 0) {
    warnings.push('Bolt result contains no changed files.');
  }

  const evidenceByKind = new Map<BoltSnapshotEvidenceKind, BoltSnapshotEvidence>();
  for (const item of result.evidence) {
    evidenceByKind.set(item.kind, {
      ...item,
      summary: safeEvidenceSummary(item.summary),
    });
  }

  for (const requiredKind of job.requiredEvidence) {
    const evidence = evidenceByKind.get(requiredKind);
    if (!evidence) {
      blockers.push(`Bolt result is missing required evidence: ${requiredKind}.`);
      continue;
    }
    if (!evidence.passed) {
      blockers.push(`Bolt evidence did not pass: ${requiredKind}.`);
    }
    if (!evidence.summary) {
      blockers.push(`Bolt evidence summary is empty: ${requiredKind}.`);
    }
  }

  return {
    allowed: blockers.length === 0,
    blockers: uniqueSorted(blockers),
    warnings: uniqueSorted(warnings),
  };
}

export function buildBoltCapabilityProbePlan(): Readonly<Record<BoltSnapshotCapability, readonly string[]>> {
  return Object.freeze({
    node: Object.freeze(['node --version']),
    terminal: Object.freeze(['command -v sh || command -v bash']),
    python: Object.freeze(['python3 --version || python --version']),
    'blender-headless': Object.freeze(['blender --background --version']),
    ninja: Object.freeze(['ninja --version']),
    'gamedev-tools': Object.freeze([
      'command -v blender || true',
      'command -v godot || true',
      'command -v unity-editor || true',
    ]),
    'git-diff': Object.freeze(['git --version']),
  });
}
