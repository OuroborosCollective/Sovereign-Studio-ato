/**
 * Draft PR Evidence Integration
 *
 * Bridges Draft PR operations with the Evidence Ledger for traceable status decisions.
 * Each draft PR preparation and creation is recorded with source, status, justification,
 * timestamp, and optional file/run-ID/path references.
 */

import {
  createEvidenceEntry,
  appendEvidenceEntry,
  type EvidenceLedger,
  type EvidenceLedgerEntry,
  type EvidenceCategory,
  type EvidenceStatus,
  type EvidenceSource,
  type EvidenceLocation,
} from './evidenceLedger';

/**
 * Draft PR preparation result mapped to evidence status
 */
export type DraftPrDecision = 'allowed' | 'blocked' | 'pending';

/**
 * Draft PR evidence metadata for richer tracking
 */
export interface DraftPrEvidenceMetadata {
  jobId: string;
  decision: DraftPrDecision;
  headBranch?: string;
  baseBranch?: string;
  canCreate: boolean;
  blockers?: string[];
  nextAction?: string;
}

/**
 * Draft PR creation result mapped to evidence status
 */
export type DraftPrCreationStatus = 'created' | 'failed' | 'verification-failed';

/**
 * Draft PR creation evidence metadata
 */
export interface DraftPrCreationMetadata {
  jobId: string;
  status: DraftPrCreationStatus;
  prUrl?: string;
  prNumber?: number;
  headSha?: string;
  publishedHeadSha?: string;
  readbackHeadSha?: string;
  branch?: string;
  ciState?: string;
  checkRunCount?: number;
  checksSuccessCount?: number;
  checksFailureCount?: number;
  checksPendingCount?: number;
}

/**
 * Map draft PR preparation decision to evidence status
 */
function decisionToStatus(decision: DraftPrDecision, canCreate: boolean): EvidenceStatus {
  if (decision === 'blocked') return 'blocked';
  if (decision === 'pending') return 'pending';
  if (!canCreate) return 'blocked';
  return 'success';
}

/**
 * Map draft PR creation status to evidence status
 */
function creationStatusToEvidenceStatus(status: DraftPrCreationStatus): EvidenceStatus {
  switch (status) {
    case 'created':
      return 'success';
    case 'failed':
      return 'failure';
    case 'verification-failed':
      return 'failure';
    default:
      return 'unknown';
  }
}

/**
 * Build reason string from preparation result
 */
function buildPreparationReason(
  decision: DraftPrDecision,
  canCreate: boolean,
  blockers?: string[],
): string {
  if (decision === 'blocked') {
    return `Draft PR preparation blocked: ${blockers?.join('; ') || 'unknown reason'}`;
  }
  if (decision === 'pending') {
    return 'Draft PR preparation pending further action';
  }
  if (!canCreate) {
    return `Draft PR preparation cannot create: ${blockers?.join('; ') || 'requirements not met'}`;
  }
  return 'Draft PR preparation allowed';
}

/**
 * Build reason string from creation result
 */
function buildCreationReason(
  status: DraftPrCreationStatus,
  prUrl?: string,
  prNumber?: number,
): string {
  switch (status) {
    case 'created':
      return `Draft PR created: ${prUrl || `PR #${prNumber}`}`;
    case 'failed':
      return 'Draft PR creation failed';
    case 'verification-failed':
      return 'Draft PR creation verification failed: incomplete GitHub readback evidence';
    default:
      return 'Draft PR creation status unknown';
  }
}

/**
 * Create evidence entry for draft PR preparation
 */
export function createDraftPrPreparationEvidence(
  metadata: DraftPrEvidenceMetadata,
): EvidenceLedgerEntry {
  const status = decisionToStatus(metadata.decision, metadata.canCreate);
  const reason = buildPreparationReason(metadata.decision, metadata.canCreate, metadata.blockers);

  return createEvidenceEntry({
    category: 'draft-pr',
    source: {
      type: 'local-runtime',
      detail: 'sovereign-agent-client.prepareDraftPr',
    },
    status,
    reason,
    location: metadata.headBranch
      ? {
          branch: metadata.headBranch,
        }
      : undefined,
    metadata: {
      jobId: metadata.jobId,
      decision: metadata.decision,
      canCreateDraftPr: metadata.canCreate,
      blockers: metadata.blockers?.join(';') || null,
      nextAction: metadata.nextAction || null,
      headBranch: metadata.headBranch || null,
      baseBranch: metadata.baseBranch || null,
    },
  });
}

/**
 * Create evidence entry for draft PR creation
 */
export function createDraftPrCreationEvidence(
  metadata: DraftPrCreationMetadata,
): EvidenceLedgerEntry {
  const status = creationStatusToEvidenceStatus(metadata.status);
  const reason = buildCreationReason(metadata.status, metadata.prUrl, metadata.prNumber);

  return createEvidenceEntry({
    category: 'draft-pr',
    source: {
      type: 'github-api',
      detail: 'sovereign-agent-client.createDraftPr',
    },
    status,
    reason,
    location: {
      url: metadata.prUrl,
      branch: metadata.branch,
      commitSha: metadata.headSha,
    },
    metadata: {
      jobId: metadata.jobId,
      creationStatus: metadata.status,
      prNumber: metadata.prNumber || null,
      headSha: metadata.headSha || null,
      publishedHeadSha: metadata.publishedHeadSha || null,
      readbackHeadSha: metadata.readbackHeadSha || null,
      ciState: metadata.ciState || null,
      checkRunCount: metadata.checkRunCount || null,
      checksSuccessCount: metadata.checksSuccessCount || null,
      checksFailureCount: metadata.checksFailureCount || null,
      checksPendingCount: metadata.checksPendingCount || null,
      shaMatch: metadata.headSha && metadata.publishedHeadSha && metadata.readbackHeadSha
        ? metadata.headSha === metadata.publishedHeadSha && metadata.headSha === metadata.readbackHeadSha
        : null,
    },
  });
}

/**
 * Append draft PR preparation evidence to a ledger
 */
export function appendDraftPrPreparationEvidence(
  ledger: EvidenceLedger,
  metadata: DraftPrEvidenceMetadata,
): EvidenceLedger {
  const entry = createDraftPrPreparationEvidence(metadata);
  return appendEvidenceEntry(ledger, entry);
}

/**
 * Append draft PR creation evidence to a ledger
 */
export function appendDraftPrCreationEvidence(
  ledger: EvidenceLedger,
  metadata: DraftPrCreationMetadata,
): EvidenceLedger {
  const entry = createDraftPrCreationEvidence(metadata);
  return appendEvidenceEntry(ledger, entry);
}

/**
 * Get the latest draft PR evidence entry from a ledger
 */
export function getLatestDraftPrEvidence(ledger: EvidenceLedger): EvidenceLedgerEntry | undefined {
  const entries = ledger.entries
    .filter((entry) => entry.category === 'draft-pr')
    .sort((a, b) => b.timestamp - a.timestamp);
  return entries[0];
}

/**
 * Check if the latest draft PR evidence indicates success
 */
export function isLatestDraftPrSuccessful(ledger: EvidenceLedger): boolean {
  const latest = getLatestDraftPrEvidence(ledger);
  return latest?.status === 'success';
}
