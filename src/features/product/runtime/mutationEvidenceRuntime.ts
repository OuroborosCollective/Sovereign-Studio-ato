/**
 * Mutation Evidence Runtime
 *
 * Declares the eight risky mutation families and provides a pure,
 * deterministic verdict deriver. Contains no Date.now(), Math.random()
 * or I/O. All timestamps must be injected by the caller.
 *
 * Mirrors the ProofRequirementSets in backend/agent_runtime/mutation_evidence_layer.py.
 * Three possible verdicts: VERIFIED | CONTRADICTED | BLOCKED_BY_MISSING_EVIDENCE
 */

export type MutationVerdict =
  | 'VERIFIED'
  | 'CONTRADICTED'
  | 'BLOCKED_BY_MISSING_EVIDENCE';

export type MutationFamily =
  | 'github_merge_release'
  | 'sovereign_rescue_repair'
  | 'mcp_registry_self_update'
  | 'docker_vps_patchmon_deployment'
  | 'postgresql_migrations_pgvector'
  | 'openrouter_freeroute_revolver'
  | 'canonical_mirror_ownership'
  | 'security_permission_change';

export type ObservationAssertion = 'OBSERVED' | 'CONTRADICTED' | 'UNAVAILABLE';

export interface MutationObservation {
  readonly requirementId: string;
  readonly evidenceKind: string;
  readonly assertion: ObservationAssertion;
  /** Epoch millis – must be injected by the caller; never generated internally. */
  readonly observedAt: number;
  readonly evidenceSha256: string;
}

export interface MutationRequirement {
  readonly requirementId: string;
  readonly evidenceKind: string;
  readonly runtimeRequired: boolean;
}

export interface MutationVerdictResult {
  readonly verdict: MutationVerdict;
  readonly satisfiedRequirements: readonly string[];
  readonly missingRequirements: readonly string[];
  readonly contradictoryRequirements: readonly string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Requirement sets – all eight mutation families
// ─────────────────────────────────────────────────────────────────────────────

export const MUTATION_REQUIREMENTS: Readonly<
  Record<MutationFamily, readonly MutationRequirement[]>
> = {
  // Family 1 – GitHub Merge, Rulesets and Release
  github_merge_release: [
    { requirementId: 'agent_run_receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
    { requirementId: 'ci_readback', evidenceKind: 'ci_readback', runtimeRequired: true },
    { requirementId: 'repository_readback', evidenceKind: 'repository_readback', runtimeRequired: true },
  ],

  // Family 2 – Sovereign Rescue and automated repairs
  sovereign_rescue_repair: [
    { requirementId: 'agent_run_receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
    { requirementId: 'repository_readback', evidenceKind: 'repository_readback', runtimeRequired: true },
  ],

  // Family 3 – MCP Registry, Broker and Self-Update
  mcp_registry_self_update: [
    { requirementId: 'agent_run_receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
    { requirementId: 'mcp_readback', evidenceKind: 'mcp_readback', runtimeRequired: true },
  ],

  // Family 4 – Docker, VPS, PatchMon and Deployment
  docker_vps_patchmon_deployment: [
    { requirementId: 'agent_run_receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
    { requirementId: 'image_readback', evidenceKind: 'image_readback', runtimeRequired: true },
    { requirementId: 'patchmon_readback', evidenceKind: 'patchmon_readback', runtimeRequired: true },
  ],

  // Family 5 – PostgreSQL Migrations and pgvector
  postgresql_migrations_pgvector: [
    { requirementId: 'agent_run_receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
    { requirementId: 'database_readback', evidenceKind: 'database_readback', runtimeRequired: true },
  ],

  // Family 6 – OpenRouter, FreeRoute and Revolver Routing
  openrouter_freeroute_revolver: [
    { requirementId: 'agent_run_receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
    { requirementId: 'runtime_readback', evidenceKind: 'runtime_readback', runtimeRequired: true },
  ],

  // Family 7 – Canonical Mirrors and Ownerships
  canonical_mirror_ownership: [
    { requirementId: 'agent_run_receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
    { requirementId: 'repository_readback', evidenceKind: 'repository_readback', runtimeRequired: true },
  ],

  // Family 8 – Security-relevant Permission Changes
  security_permission_change: [
    { requirementId: 'agent_run_receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
    { requirementId: 'ci_readback', evidenceKind: 'ci_readback', runtimeRequired: true },
    { requirementId: 'runtime_readback', evidenceKind: 'runtime_readback', runtimeRequired: true },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Pure, deterministic verdict deriver
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Derive a mutation verdict from a set of observations and requirements.
 *
 * Pure function: no I/O, no Date.now(), no Math.random().
 * Fail-closed rules:
 *   - Any CONTRADICTED observation on a runtime_required requirement_id → CONTRADICTED.
 *   - Any runtime_required requirement_id with no OBSERVED assertion → BLOCKED_BY_MISSING_EVIDENCE.
 *   - All runtime_required requirement_ids satisfied with OBSERVED → VERIFIED.
 *
 * CONTRADICTED is sticky: a later OBSERVED for the same requirement_id
 * cannot override a prior CONTRADICTED.
 */
export function deriveMutationVerdict(
  requirements: readonly MutationRequirement[],
  observations: readonly MutationObservation[],
): MutationVerdictResult {
  // Build a final assertion map; CONTRADICTED is sticky.
  const assertionByRequirementId = new Map<string, ObservationAssertion>();
  for (const obs of observations) {
    const existing = assertionByRequirementId.get(obs.requirementId);
    if (existing === 'CONTRADICTED') continue;
    assertionByRequirementId.set(obs.requirementId, obs.assertion);
  }

  const satisfied: string[] = [];
  const missing: string[] = [];
  const contradictory: string[] = [];

  for (const req of requirements) {
    if (!req.runtimeRequired) continue;
    const assertion = assertionByRequirementId.get(req.requirementId);
    if (assertion === 'CONTRADICTED') {
      contradictory.push(req.requirementId);
    } else if (assertion === 'OBSERVED') {
      satisfied.push(req.requirementId);
    } else {
      // UNAVAILABLE or absent → missing (fail-closed)
      missing.push(req.requirementId);
    }
  }

  let verdict: MutationVerdict;
  if (contradictory.length > 0) {
    verdict = 'CONTRADICTED';
  } else if (missing.length > 0) {
    verdict = 'BLOCKED_BY_MISSING_EVIDENCE';
  } else {
    verdict = 'VERIFIED';
  }

  return {
    verdict,
    satisfiedRequirements: satisfied,
    missingRequirements: missing,
    contradictoryRequirements: contradictory,
  };
}

/**
 * Convenience: derive verdict for a named mutation family using the
 * built-in MUTATION_REQUIREMENTS registry.
 */
export function deriveFamilyVerdict(
  family: MutationFamily,
  observations: readonly MutationObservation[],
): MutationVerdictResult {
  const requirements = MUTATION_REQUIREMENTS[family];
  return deriveMutationVerdict(requirements, observations);
}

/**
 * All eight canonical mutation family identifiers.
 */
export const MUTATION_FAMILIES: readonly MutationFamily[] = [
  'github_merge_release',
  'sovereign_rescue_repair',
  'mcp_registry_self_update',
  'docker_vps_patchmon_deployment',
  'postgresql_migrations_pgvector',
  'openrouter_freeroute_revolver',
  'canonical_mirror_ownership',
  'security_permission_change',
];
