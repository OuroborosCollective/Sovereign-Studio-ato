/**
 * chatClaimGuard - Prevents unverified claims from appearing in chat.
 *
 * Rule: No agent response may claim successful work unless the matching
 * runtime field is populated in AgentWorkSnapshot.
 *
 * Invariants enforced:
 * - "PR erstellt" / "Draft PR bereit"  → draftPrUrl must exist
 * - "Branch erstellt"                  → branchName must exist
 * - "Commit erstellt"                  → commitSha must exist
 * - "Executor läuft" / "Sovereign Agent…" → jobId and executor state must exist
 */

import type { AgentWorkSnapshot } from './agentWorkRuntime';

export type ClaimViolation =
  | 'draft_pr_claimed_without_url'
  | 'branch_claimed_without_name'
  | 'commit_claimed_without_sha'
  | 'executor_claimed_without_job'
  | 'deployment_claimed_without_revision_digest'
  | 'live_claimed_without_runtime_health'
  | 'all_tests_claimed_without_complete_evidence';

export interface RuntimeClaimEvidence {
  readonly deployedRevision?: string;
  readonly imageDigest?: string;
  readonly runtimeHealthy?: boolean;
  readonly testsPassed?: boolean;
  readonly skippedTests?: number;
}

export interface ClaimGuardResult {
  readonly allowed: boolean;
  readonly violations: readonly ClaimViolation[];
  readonly honestFallback: string | null;
}

const CLAIM_PATTERNS: Array<{
  readonly pattern: RegExp;
  readonly violation: ClaimViolation;
  readonly check: (snapshot: AgentWorkSnapshot, evidence: RuntimeClaimEvidence) => boolean;
}> = [
  {
    pattern: /\b(pr erstellt|draft pr bereit|pull request erstellt|pr is ready)\b/i,
    violation: 'draft_pr_claimed_without_url',
    check: (s) => typeof s.draftPrUrl === 'string' && s.draftPrUrl.startsWith('http'),
  },
  {
    pattern: /\bbranch erstellt\b/i,
    violation: 'branch_claimed_without_name',
    check: (s) => typeof s.branchName === 'string' && s.branchName.trim().length > 0,
  },
  {
    pattern: /\bcommit erstellt\b/i,
    violation: 'commit_claimed_without_sha',
    check: (s) => typeof s.commitSha === 'string' && s.commitSha.trim().length > 0,
  },
  {
    pattern: /\b(executor läuft|sovereign-agent arbeitet|sovereign agent arbeitet|sovereign agent läuft|job läuft|job started)\b/i,
    violation: 'executor_claimed_without_job',
    check: (s) =>
      typeof s.jobId === 'string' &&
      s.jobId.trim().length > 0 &&
      (s.state === 'executor_running' || s.state === 'executor_starting'),
  },
  {
    pattern: /\b(auf dem vps installiert|deployed|deployment abgeschlossen|in produktion installiert)\b/i,
    violation: 'deployment_claimed_without_revision_digest',
    check: (_s, evidence) => /^[0-9a-f]{40}$/i.test(evidence.deployedRevision ?? '') && /^sha256:[0-9a-f]{64}$/i.test(evidence.imageDigest ?? ''),
  },
  {
    pattern: /\b(live verfügbar|jetzt live|production ready|produktiv verfügbar)\b/i,
    violation: 'live_claimed_without_runtime_health',
    check: (_s, evidence) => evidence.runtimeHealthy === true && /^[0-9a-f]{40}$/i.test(evidence.deployedRevision ?? '') && /^sha256:[0-9a-f]{64}$/i.test(evidence.imageDigest ?? ''),
  },
  {
    pattern: /\b(alle tests bestanden|all tests passed|sämtliche tests grün)\b/i,
    violation: 'all_tests_claimed_without_complete_evidence',
    check: (_s, evidence) => evidence.testsPassed === true && (evidence.skippedTests ?? 0) === 0,
  },
];

function honestFallbackFor(violations: readonly ClaimViolation[], snapshot: AgentWorkSnapshot): string {
  const parts: string[] = ['Das kann ich noch nicht bestätigen.'];
  parts.push(`Aktueller Runtime-State: ${snapshot.state}${snapshot.state === 'idle' ? ' (kein laufender Job)' : ''}.`);

  if (violations.includes('draft_pr_claimed_without_url')) {
    parts.push('Draft PR URL liegt noch nicht vor.');
  }
  if (violations.includes('branch_claimed_without_name')) {
    parts.push('Branch-Name wurde noch nicht verifiziert.');
  }
  if (violations.includes('commit_claimed_without_sha')) {
    parts.push('Commit-SHA liegt noch nicht vor.');
  }
  if (violations.includes('executor_claimed_without_job')) {
    parts.push('Kein laufender Job belegt.');
  }
  if (violations.includes('deployment_claimed_without_revision_digest')) {
    parts.push('Deployment-Revision und unveränderlicher Image-Digest sind nicht gemeinsam belegt.');
  }
  if (violations.includes('live_claimed_without_runtime_health')) {
    parts.push('Ein produktiver Runtime-Health-Readback liegt nicht vollständig vor.');
  }
  if (violations.includes('all_tests_claimed_without_complete_evidence')) {
    parts.push('Die Test-Evidence ist unvollständig oder enthält übersprungene Prüfungen.');
  }

  return parts.join(' ');
}

export function checkChatClaim(
  responseText: string,
  snapshot: AgentWorkSnapshot,
  evidence: RuntimeClaimEvidence = {},
): ClaimGuardResult {
  const violations: ClaimViolation[] = [];

  for (const entry of CLAIM_PATTERNS) {
    if (entry.pattern.test(responseText) && !entry.check(snapshot, evidence)) {
      violations.push(entry.violation);
    }
  }

  if (violations.length === 0) {
    return { allowed: true, violations: [], honestFallback: null };
  }

  return {
    allowed: false,
    violations,
    honestFallback: honestFallbackFor(violations, snapshot),
  };
}

export function hasAnyWorkClaim(responseText: string): boolean {
  return CLAIM_PATTERNS.some((entry) => entry.pattern.test(responseText));
}
