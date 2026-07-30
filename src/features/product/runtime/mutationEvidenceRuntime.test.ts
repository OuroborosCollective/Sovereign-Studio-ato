import { describe, expect, it } from 'vitest';
import {
  MUTATION_FAMILIES,
  MUTATION_REQUIREMENTS,
  deriveFamilyVerdict,
  deriveMutationVerdict,
  type MutationFamily,
  type MutationObservation,
  type MutationRequirement,
} from './mutationEvidenceRuntime';

// Injected fixed timestamp – no Date.now() in tests.
const FIXED_AT = 1753900000000;
const FIXED_SHA = 'a'.repeat(64);

function obs(
  requirementId: string,
  assertion: MutationObservation['assertion'] = 'OBSERVED',
): MutationObservation {
  return {
    requirementId,
    evidenceKind: requirementId,
    assertion,
    observedAt: FIXED_AT,
    evidenceSha256: FIXED_SHA,
  };
}

function fullObsForFamily(family: MutationFamily): MutationObservation[] {
  return MUTATION_REQUIREMENTS[family].map((r) => obs(r.requirementId));
}

// ─────────────────────────────────────────────────────────────────────────────
// deriveMutationVerdict – core logic
// ─────────────────────────────────────────────────────────────────────────────

describe('deriveMutationVerdict', () => {
  const requirements: readonly MutationRequirement[] = [
    { requirementId: 'receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
    { requirementId: 'ci', evidenceKind: 'ci_readback', runtimeRequired: true },
  ];

  it('returns VERIFIED when all required observations are OBSERVED', () => {
    const result = deriveMutationVerdict(requirements, [obs('receipt'), obs('ci')]);
    expect(result.verdict).toBe('VERIFIED');
    expect(result.satisfiedRequirements).toContain('receipt');
    expect(result.satisfiedRequirements).toContain('ci');
    expect(result.missingRequirements).toHaveLength(0);
    expect(result.contradictoryRequirements).toHaveLength(0);
  });

  it('returns BLOCKED_BY_MISSING_EVIDENCE when a required observation is absent', () => {
    const result = deriveMutationVerdict(requirements, [obs('receipt')]);
    expect(result.verdict).toBe('BLOCKED_BY_MISSING_EVIDENCE');
    expect(result.missingRequirements).toContain('ci');
    expect(result.satisfiedRequirements).toContain('receipt');
  });

  it('returns BLOCKED_BY_MISSING_EVIDENCE when a required observation is UNAVAILABLE', () => {
    const result = deriveMutationVerdict(requirements, [obs('receipt'), obs('ci', 'UNAVAILABLE')]);
    expect(result.verdict).toBe('BLOCKED_BY_MISSING_EVIDENCE');
    expect(result.missingRequirements).toContain('ci');
  });

  it('returns CONTRADICTED when any observation carries CONTRADICTED assertion', () => {
    const result = deriveMutationVerdict(requirements, [
      obs('receipt'),
      obs('ci', 'CONTRADICTED'),
    ]);
    expect(result.verdict).toBe('CONTRADICTED');
    expect(result.contradictoryRequirements).toContain('ci');
  });

  it('CONTRADICTED is sticky: a later OBSERVED cannot override it', () => {
    const result = deriveMutationVerdict(requirements, [
      obs('receipt'),
      obs('ci', 'CONTRADICTED'),
      obs('ci', 'OBSERVED'),
    ]);
    expect(result.verdict).toBe('CONTRADICTED');
    expect(result.contradictoryRequirements).toContain('ci');
  });

  it('CONTRADICTED takes priority over BLOCKED_BY_MISSING_EVIDENCE', () => {
    // ci CONTRADICTED, receipt absent → CONTRADICTED wins
    const result = deriveMutationVerdict(requirements, [obs('ci', 'CONTRADICTED')]);
    expect(result.verdict).toBe('CONTRADICTED');
  });

  it('returns BLOCKED_BY_MISSING_EVIDENCE with empty observations (fail-closed)', () => {
    const result = deriveMutationVerdict(requirements, []);
    expect(result.verdict).toBe('BLOCKED_BY_MISSING_EVIDENCE');
    expect(result.missingRequirements).toHaveLength(2);
  });

  it('ignores non-runtime_required requirements', () => {
    const mixed: readonly MutationRequirement[] = [
      { requirementId: 'receipt', evidenceKind: 'agent_run_receipt', runtimeRequired: true },
      { requirementId: 'optional', evidenceKind: 'optional_hint', runtimeRequired: false },
    ];
    // Only 'receipt' is runtime_required; 'optional' absent should not block.
    const result = deriveMutationVerdict(mixed, [obs('receipt')]);
    expect(result.verdict).toBe('VERIFIED');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// MUTATION_REQUIREMENTS registry completeness
// ─────────────────────────────────────────────────────────────────────────────

describe('MUTATION_REQUIREMENTS', () => {
  it('defines exactly eight mutation families', () => {
    expect(Object.keys(MUTATION_REQUIREMENTS)).toHaveLength(8);
  });

  it('all eight families are present in MUTATION_FAMILIES', () => {
    expect(MUTATION_FAMILIES).toHaveLength(8);
    for (const family of MUTATION_FAMILIES) {
      expect(MUTATION_REQUIREMENTS[family]).toBeDefined();
    }
  });

  it('every family requires agent_run_receipt', () => {
    for (const family of MUTATION_FAMILIES) {
      const ids = MUTATION_REQUIREMENTS[family].map((r) => r.requirementId);
      expect(ids).toContain('agent_run_receipt');
    }
  });

  it('every family has at least two requirements', () => {
    for (const family of MUTATION_FAMILIES) {
      expect(MUTATION_REQUIREMENTS[family].length).toBeGreaterThanOrEqual(2);
    }
  });

  it('all requirements are runtime_required', () => {
    for (const family of MUTATION_FAMILIES) {
      for (const req of MUTATION_REQUIREMENTS[family]) {
        expect(req.runtimeRequired).toBe(true);
      }
    }
  });

  it('requirement_ids are unique within each family', () => {
    for (const family of MUTATION_FAMILIES) {
      const ids = MUTATION_REQUIREMENTS[family].map((r) => r.requirementId);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// deriveFamilyVerdict – per-family VERIFIED path
// ─────────────────────────────────────────────────────────────────────────────

describe('deriveFamilyVerdict – VERIFIED path', () => {
  for (const family of [
    'github_merge_release',
    'sovereign_rescue_repair',
    'mcp_registry_self_update',
    'docker_vps_patchmon_deployment',
    'postgresql_migrations_pgvector',
    'openrouter_freeroute_revolver',
    'canonical_mirror_ownership',
    'security_permission_change',
  ] as MutationFamily[]) {
    it(`${family}: full evidence → VERIFIED`, () => {
      const result = deriveFamilyVerdict(family, fullObsForFamily(family));
      expect(result.verdict).toBe('VERIFIED');
      expect(result.missingRequirements).toHaveLength(0);
      expect(result.contradictoryRequirements).toHaveLength(0);
    });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Fail-closed: no family can reach VERIFIED with empty observations
// ─────────────────────────────────────────────────────────────────────────────

describe('deriveFamilyVerdict – fail-closed', () => {
  it('no family reaches VERIFIED with empty observations', () => {
    for (const family of MUTATION_FAMILIES) {
      const result = deriveFamilyVerdict(family, []);
      expect(result.verdict).toBe('BLOCKED_BY_MISSING_EVIDENCE');
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Family-specific structural checks
// ─────────────────────────────────────────────────────────────────────────────

describe('family-specific requirement sets', () => {
  it('github_merge_release requires ci_readback and repository_readback', () => {
    const ids = MUTATION_REQUIREMENTS.github_merge_release.map((r) => r.requirementId);
    expect(ids).toContain('ci_readback');
    expect(ids).toContain('repository_readback');
  });

  it('docker_vps_patchmon_deployment requires image_readback and patchmon_readback', () => {
    const ids = MUTATION_REQUIREMENTS.docker_vps_patchmon_deployment.map((r) => r.requirementId);
    expect(ids).toContain('image_readback');
    expect(ids).toContain('patchmon_readback');
  });

  it('security_permission_change requires ci_readback and runtime_readback', () => {
    const ids = MUTATION_REQUIREMENTS.security_permission_change.map((r) => r.requirementId);
    expect(ids).toContain('ci_readback');
    expect(ids).toContain('runtime_readback');
  });

  it('mcp_registry_self_update requires mcp_readback', () => {
    const ids = MUTATION_REQUIREMENTS.mcp_registry_self_update.map((r) => r.requirementId);
    expect(ids).toContain('mcp_readback');
  });

  it('postgresql_migrations_pgvector requires database_readback', () => {
    const ids = MUTATION_REQUIREMENTS.postgresql_migrations_pgvector.map((r) => r.requirementId);
    expect(ids).toContain('database_readback');
  });

  it('github_merge_release: BLOCKED when ci_readback is missing', () => {
    const observations = fullObsForFamily('github_merge_release').filter(
      (o) => o.requirementId !== 'ci_readback',
    );
    const result = deriveFamilyVerdict('github_merge_release', observations);
    expect(result.verdict).toBe('BLOCKED_BY_MISSING_EVIDENCE');
    expect(result.missingRequirements).toContain('ci_readback');
  });

  it('security_permission_change: CONTRADICTED blocks even when other evidence is present', () => {
    const result = deriveFamilyVerdict('security_permission_change', [
      obs('agent_run_receipt'),
      obs('ci_readback', 'CONTRADICTED'),
      obs('runtime_readback'),
    ]);
    expect(result.verdict).toBe('CONTRADICTED');
    expect(result.contradictoryRequirements).toContain('ci_readback');
  });
});
