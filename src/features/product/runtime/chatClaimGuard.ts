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
  | 'executor_claimed_without_job';

export interface ClaimGuardResult {
  readonly allowed: boolean;
  readonly violations: readonly ClaimViolation[];
  readonly honestFallback: string | null;
}

const CLAIM_PATTERNS: Array<{
  readonly pattern: RegExp;
  readonly violation: ClaimViolation;
  readonly check: (snapshot: AgentWorkSnapshot) => boolean;
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

  return parts.join(' ');
}

export function checkChatClaim(
  responseText: string,
  snapshot: AgentWorkSnapshot,
): ClaimGuardResult {
  const violations: ClaimViolation[] = [];

  for (const entry of CLAIM_PATTERNS) {
    if (entry.pattern.test(responseText) && !entry.check(snapshot)) {
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
