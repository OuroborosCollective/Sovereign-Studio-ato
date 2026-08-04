---
name: sovereign-preflight
description: Bind continuity, exact revision, capabilities, effects, approval requirements, and evidence before selecting or executing Sovereign MCP tools.
triggers:
  - sovereign preflight
  - plan MCP work
  - select sovereign tools
  - start repository integration
---

# Sovereign preflight

Use this skill before every multi-step task and before any action that can write to a workspace or an external system.

1. Read the canonical continuity context with `sovereign_continuity_context_read`.
2. Resolve the exact repository/workspace/PR/runtime revision tuple with `repository_revision_resolve` when repository work is involved.
3. Run `sovereign_mission_preflight` with explicit capabilities, allowed effects, and required evidence.
4. Treat the resulting ToolChain as a non-executing proposal. Validate contracts and bind every required input before advancing.
5. Prefer read-only inventory and diagnosis tools before workspace writes; prefer workspace writes before external writes.
6. Evaluate owner approval, revision binding, payload binding, and expiry before protected actions.
7. Stop and re-plan when the failure family changes or evidence identities no longer match.

Never infer authorization from tool availability. Never treat a plan, snapshot, UI badge, or prior success as current runtime evidence.

See `../../references/operational-skills.snapshot.json` for source-revision skill identities and `../../references/tool-registry.snapshot.txt` for exact registered tool names.
