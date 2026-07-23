# Sovereign MCP Optimal Operation

## Purpose

Make mission-first, contract-bound and evidence-first operation persistent across ChatGPT sessions and MCP revisions. This skill is not a conversational preference. Its authoritative contract is the versioned operating profile at `tools/sovereign-chatgpt-mcp/config/sovereign-mcp-operating-profile.json`, and its runtime enforcement is implemented by `operating_profile.py`.

## Required operating sequence

For multi-step or mutating work:

1. Resolve the exact repository, workspace, PR, CI and deployed MCP revision before changing state.
2. Read the live MCP registry rather than relying on remembered tool names or stale documentation.
3. Translate the user mission into structured capabilities, allowed effect classes and required evidence.
4. Select the smallest eligible registered tool set.
5. Compile a non-executing MCP toolchain and validate it against the same live registry snapshot.
6. Execute only one separately governed tool call at a time.
7. Stop when the revision, failure family, effect class, owner gate or required evidence changes.
8. Verify every claimed effect through its authoritative producer and readback surface.
9. Persist a learning pattern only after the relevant tests, deployment and runtime canary have proven the outcome.

## Runtime enforcement

`sovereign_operating_profile_status` reports the loaded profile version and digest, current registry digest, required governance-tool coverage, output-schema coverage, forbidden-tool drift and mutation-wrapper installation.

`sovereign_mission_preflight` performs the mission-level routing, non-executing toolchain compilation and live validation. It never calls the proposed tools.

Every registered workspace-write or external-write tool is wrapped after output contracts are installed. Before the original function runs, the wrapper verifies:

- the versioned operating profile loads and passes structural checks;
- all required governance tools remain registered;
- the live registry is complete and every tool has an explicit output schema;
- the target tool remains registered with its declared effect and contract hash;
- a single-tool contract chain validates against the current registry snapshot;
- owner approval is true when the target schema exposes `owner_approved`;
- exact revision fields contain a full 40-character Git SHA when present;
- confirmation fields are non-empty when present;
- mutation arguments do not contain recognized secret-shaped values.

Any failed check blocks the mutation before the original tool function is called and returns a machine-readable failure envelope.

## Non-negotiable boundaries

- Natural-language understanding belongs to the online LLM. Runtime code enforces actions, policy, permissions, state and evidence; it does not imitate semantic understanding through keyword rules.
- No generic shell, arbitrary SQL surface, Docker socket or invented tool contract may be introduced as an operational shortcut.
- No mock, stub, facade, cached UI projection or unchecked return value may be called live truth.
- FreeLLM and Paid OpenRouter/LiteLLM routes stay separate. There is no automatic Free-to-Paid or Paid-to-Free fallback.
- Protected values never enter chat, MCP arguments, logs, repository files or database rows. They use the authenticated owner-input path only.
- A release claim requires exact revision, required CI on that revision, immutable digest, deployment readback and a runtime protocol canary.
- Learning is written only after a proven result and remains bounded, secret-free and revision-linked.

## Completion definition

The profile is technically live only when all of the following are true for the same immutable MCP revision:

- repository tests for profile loading, mission preflight and mutation blocking are green;
- every MCP tool exposes an output schema;
- the operating-profile status tool returns `OPERATING_PROFILE_ENFORCED`;
- the mutation enforcement installer reports all mutable tools wrapped;
- the immutable MCP image contains the profile, skill and enforcement module;
- the VPS installer verifies the profile status and wrapper report inside the running container;
- MCP initialize, tools/list and broker RPC canaries are green;
- the installed revision and image digest match the merged revision.

Anything less is pending, blocked or only repository-level implementation evidence.
