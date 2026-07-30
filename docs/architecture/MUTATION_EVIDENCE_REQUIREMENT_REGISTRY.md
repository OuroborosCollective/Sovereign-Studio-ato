# Mutation Evidence Requirement Registry

## Purpose

This registry binds the eight high-risk operation families from issue #1097 to versioned `ProofRequirementSet` contracts. It is a thin extension of the pure verdict core introduced by issue #1098.

The registry does **not** collect evidence, execute or authorize mutations, persist a new truth store, access network or database resources, or independently calculate a verdict. `evaluate_mutation_evidence` delegates exclusively to `proof_verdict.evaluate_proof`.

## Declared families

1. `github_merge_release`
2. `sovereign_rescue_repair`
3. `mcp_registry_self_update`
4. `fleet_deployment`
5. `postgres_pgvector_mutation`
6. `provider_routing_mutation`
7. `canonical_mirror_ownership`
8. `security_permission_change`

Each family is versioned independently through an immutable `ProofRequirementSet`. The deterministic registry projection exposes each requirement-set SHA-256 and a registry SHA-256 calculated through the existing canonical no-float proof contract.

## Truth boundaries

- Missing required observations remain `BLOCKED_BY_MISSING_EVIDENCE`.
- Revision, operation, input or diff mismatches remain `CONTRADICTED`.
- Static candidates cannot satisfy runtime-required observations.
- The provider family keeps OpenRouter paid and FreeRoute/FreeLLM runtime truth separate and includes a static no-LiteLLM contract without treating it as a route canary.
- PostgreSQL and pgvector share one database truth domain; Arelorian Wasd remains excluded through the required domain-isolation observation.
- Mirror and ownership checks are repository readbacks, not runtime capability claims.
- A proof verdict never authorizes an automatic merge, deployment, migration, provider activation or permission change by itself.

## Deferred integrations

The following remain explicitly outside this registry PR:

- evidence collectors and `CapabilityDelta` production: #1099
- Rescue and GitHub write-path enforcement: #1100
- MCP, Docker, PatchMon and deployment enforcement: #1101
- PostgreSQL and provider enforcement: #1102
- exact-head observe/enforce rollout and runtime certification: #1103

No collector or protected mutation path is enabled by the registry alone.

## Canonical ownership

The canonical implementation is `backend/agent_runtime/mutation_evidence_layer.py`. The deployment mirror is `scripts/sovereign-backend/agent_runtime/mutation_evidence_layer.py`; both files and both package export files must remain byte-identical.
