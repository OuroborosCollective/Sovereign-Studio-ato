# Sovereign MCP Toolset – OpenHands Plugin Preview

This directory is a repository-only, inactive OpenHands plugin projection of the existing Sovereign MCP tool registry.

It does **not** replace, fork, embed, install, deploy, or start the production MCP. It contains no production endpoint, no secret, no executable hook, no workflow registration, no Docker integration, and no VPS installation path.

## Purpose

OpenHands plugins can bundle a manifest, skills, hooks, agents, commands, and MCP configuration. This package maps those extension surfaces onto the existing Sovereign MCP without copying its Python runtime or creating a second truth source:

- `.plugin/plugin.json` identifies the portable plugin.
- `skills/*/SKILL.md` provides progressive operational guidance.
- `agents/` contains a bounded evidence-first operator profile.
- `commands/` exposes explicit inventory and preflight entry points.
- `hooks/hooks.json` is deliberately empty.
- `.mcp.json.example` is a non-active template only.
- `references/` preserves exact source-revision inventories and migration boundaries.
- `scripts/validate_package.py` validates isolation and package integrity without network access.

## Truth boundary

OpenHands may discover MCP tools dynamically after a separately configured remote MCP connection is established. The tools are not implemented in this plugin. Their contracts, effects, authorization, runtime state, and evidence remain owned by the existing Sovereign MCP registry.

The snapshots in `references/` prove only what was observed at source revision `6bd7a99c04642e095919593365325681a9b0a636`:

- 231 registered MCP tool names.
- Registry snapshot SHA-256 `936c05f72a2e4843aa84581524fb4ce24381ddf896bceebaaf8d348458c1d1e4`.
- 44 operational skills mapped to 50 unique tool identities.

A snapshot is not runtime readiness. Every operation still requires fresh revision, registry, authorization, CI, deployment, container, database, or PatchMon evidence appropriate to the mission.

## Inactive by design

The repository contains `.mcp.json.example`, not `.mcp.json`. OpenHands therefore receives no MCP server registration from this package in its committed state.

Activation is intentionally external to this repository change:

1. Copy this package into a separate consumer workspace or configure it through an owner-approved OpenHands plugin source.
2. Copy `.mcp.json.example` to `.mcp.json` only in that isolated consumer environment.
3. Replace the placeholder with an owner-approved HTTPS MCP endpoint and the required authentication configuration.
4. Validate the remote registry and exact revision before allowing any mutation.

Never commit tokens, API keys, cookies, private URLs, or protected owner values.

## Provider rule

The current registry still exposes several `litellm_*` names as retired compatibility tombstones. They are not active provider guidance in this package. Direct paid routing uses OpenRouter contracts (`openrouter_provider_status`, `openrouter_provider_activate`); managed free routes use the `freellm_*` contracts.

## Validation

Run from the repository root:

```bash
python3 integrations/openhands/sovereign-mcp-toolset-plugin/scripts/validate_package.py
```

The validator checks manifest fields, JSON syntax, empty hooks, absence of active MCP configuration, snapshot counts and hashes, skill frontmatter, forbidden paths, and the repository-only activation boundary.

## Production exclusion

The production MCP Dockerfile copies an explicit allowlist from `tools/sovereign-chatgpt-mcp/`. This package lives under `integrations/openhands/` and is not referenced by the Dockerfile, launcher, workflow, Compose, backend, deployment, or VPS installation paths.
