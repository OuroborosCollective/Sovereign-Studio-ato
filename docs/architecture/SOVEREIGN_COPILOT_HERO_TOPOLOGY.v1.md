# Sovereign Copilot HERO Topology v1

## Status

`IMPLEMENTED_IN_REPOSITORY` only after this document and its referenced files exist at an exact revision. GitHub default-branch availability, CI, production runtime and Sovereign MCP deployment remain separate truth classes.

## Purpose

Provide one user-facing GitHub Copilot custom agent for Sovereign Studio ATO while preserving the repository's existing truth, authority, MCP, evidence and continuity owners.

The topology is an orchestration layer, not a new Sovereign runtime.

```text
User
  |
  v
Sovereign Overlord HERO-1
  |
  +--> Sovereign Architect        (read-only architecture investigation)
  +--> Sovereign Implementer      (bounded workspace implementation)
  +--> Sovereign Verifier         (independent evidence judge)
  +--> Sovereign Runtime Verifier (runtime/readback judge; no simulated live evidence)
  +--> Sovereign Security Reviewer(read-only adversarial review)
  |
  v
Existing repository / CI / MCP / runtime truth owners
```

## First-class invariant

Only `.github/agents/sovereign-overlord-hero-1.agent.md` is directly user-invocable. Specialist profiles are internal (`user-invocable: false`) and disabled for automatic model selection. The HERO owns task decomposition and reconciliation; specialist output is advisory/evidence input and cannot itself create target-system truth.

## Canonical truth ownership

The Copilot layer must defer to:

- `AGENTS.md` for repository-wide agent/change/evidence rules;
- `docs/SOVEREIGN_PRODUCT_TRUTH.md` for product truth classes and readback requirements;
- `.github/copilot-instructions.md` for repository Copilot behavior;
- `tools/sovereign-chatgpt-mcp/config/sovereign-mcp-operating-profile.json` and its runtime enforcement for the live Sovereign MCP control plane;
- `tools/sovereign-chatgpt-mcp/skills/` for canonical MCP operational skills;
- continuity context, policy and append-only ledger for repository-finalization continuity.

`.github/skills/` are discovery/adaptation wrappers. They must not duplicate or supersede MCP runtime policy.

## Delegation boundary

The HERO has the `agent` capability so it can delegate bounded work. Internal specialists deliberately do not have `agent`; this prevents recursive hidden swarms from becoming an uncontrolled second orchestrator.

Recommended separation:

1. Architect maps canonical ownership, mirrors, impact and required evidence.
2. Implementer applies the smallest causal patch and tests it.
3. Security reviewer challenges authority/supply-chain/evidence boundaries.
4. Verifier independently judges repository/test/CI evidence.
5. Runtime verifier independently judges artifact/deployment/container/PatchMon/database/provider readback when such live tools actually exist in the session.
6. HERO reconciles conflicts against authoritative sources and returns scoped truth classes.

## Skills

Project-level Copilot skills cover:

- mission control and exact-revision planning;
- the four-sensor architecture radar;
- runtime/target-system readback discipline;
- final evidence verdict classification.

They are intentionally compact. Detailed live MCP operation remains canonical under `tools/sovereign-chatgpt-mcp/skills/sovereign-mcp-optimal-operation/SKILL.md` and related runtime skills.

## Hook guardrail

`.github/hooks/sovereign-guardrails.json` installs a `preToolUse` command hook for shell tools. The local stdlib-only guard rejects a narrow set of repository-forbidden execution shortcuts:

- remote download piped directly into a shell;
- copying a local patch directly into a running Docker container;
- installing packages inside a running Docker container.

The hook does not inspect network resources, does not log tool arguments and does not claim success. It is a pre-execution guard only.

GitHub hook timeouts are fail-open by platform contract, so the guard is deliberately local and tiny with a five-second timeout. The CI validator exercises explicit allow/deny and malformed-input behavior. A hook result is never runtime evidence.

## Validation contract

`scripts/validate-sovereign-copilot-customization.py` checks without third-party Python dependencies that:

- every custom-agent filename uses the valid `*.agent.md` form;
- the obsolete space-containing HERO file is absent;
- exactly one Sovereign profile is user-invocable;
- HERO retains `agent` and `github/*` tools;
- specialists remain hidden/non-recursive;
- agent prompts remain within the GitHub profile size contract;
- required project skills have valid frontmatter;
- hook JSON is version 1 and scoped to shell tools;
- safe shell work is allowed while repository-forbidden shortcut examples are denied;
- malformed hook input fails closed at script level.

`.github/workflows/sovereign-copilot-customization.yml` runs this contract for relevant pull requests and pushes to `main`.

## Provider and project boundaries

This topology does not create an LLM provider transport. Existing direct OpenRouter paid and direct free-route/Revolver contracts remain authoritative. LiteLLM is not reintroduced.

Sovereign Studio ATO remains separate from Arelorian WASD and OuroborosEngine. No game-runtime truth is imported by this configuration.

## Completion evidence

A full repository integration claim requires at least:

1. exact source/base and candidate head revisions;
2. expected files and valid profile names read back from GitHub;
3. validator success at that candidate revision;
4. exact-head GitHub CI success for required gates;
5. continuity completion evidence before repository finalization;
6. merge exact-head and fresh `main` readback if the owner-authorized merge is performed.

This GitHub customization alone never proves production backend, MCP, database, provider, Docker or PatchMon runtime state.