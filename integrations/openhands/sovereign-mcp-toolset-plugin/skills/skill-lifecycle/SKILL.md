---
name: skill-lifecycle
description: Inventory, validate, compare, map, benchmark, and deprecate skill bundles without activating untrusted code or duplicating covered MCP capabilities.
triggers:
  - inspect skill bundle
  - add MCP skill
  - compare skill candidates
  - deprecate tool
---

# Skill lifecycle

Inspect imported skill archives without executing them. Validate metadata, structure, unsafe paths, secret material, shell behavior, and dynamic-execution risk before extracting capability candidates.

Map requested architecture tasks to the live registry with `skill_capability_coverage_map` before creating a new skill. Prefer guidance that composes existing tool contracts over duplicate tools or parallel runtimes.

For a validated candidate, generate only non-active contract previews until ownership, permissions, regression missions, and supply-chain provenance are reviewed. Benchmark safe missions against expected tool calls, allowed effects, and required evidence.

Manage lifecycle states explicitly: experimental, active, restricted, deprecated, and removed. Block deprecation or removal when active callers or unresolved replacements remain. Preserve tombstones where compatibility requires them, but do not present retired names as active implementations.

This plugin's skills are Markdown guidance. They cannot prove that a remote tool exists or is ready; verify the live registry on every relevant session.
