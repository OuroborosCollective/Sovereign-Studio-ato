# OpenHands migration map

## Source

- Repository: `OuroborosCollective/Sovereign-Studio-ato`
- Source revision: `6bd7a99c04642e095919593365325681a9b0a636`
- Existing MCP source/build directory: `tools/sovereign-chatgpt-mcp/`
- Observed registry: 231 tools, snapshot `936c05f72a2e4843aa84581524fb4ce24381ddf896bceebaaf8d348458c1d1e4`

## Mapping

| OpenHands extension surface | Migrated repository artifact | Sovereign source of truth |
| --- | --- | --- |
| Plugin manifest | `.plugin/plugin.json` | Package identity only |
| Skills | `skills/*/SKILL.md` | Live MCP contracts and operational skill inventory |
| Hooks | `hooks/hooks.json` | Empty; no automatic execution |
| MCP configuration | `.mcp.json.example` | Existing owner-approved remote MCP endpoint |
| Agents | `agents/sovereign-evidence-operator.md` | Existing policy, approval, preflight, and evidence tools |
| Commands | `commands/*.md` | Explicit read-only inventory/preflight entry points |
| Tool catalog | `references/tool-registry.snapshot.txt` | `mcp_tool_contract_registry` live readback |
| Skill catalog | `references/operational-skills.snapshot.json` | `operational_skill_inventory` live readback |
| Validation | `scripts/validate_package.py` | Repository-only structural evidence |

## Capability grouping

The 231 exact tool names are preserved in the registry snapshot and exposed through the following progressive guidance families. These counts are classification aids, not separate runtime registries:

| Family | Approximate tool count | OpenHands skill |
| --- | ---: | --- |
| Repository and CI | 50 | `repository-evidence` |
| MCP governance and skill lifecycle | 34 | `mcp-governance`, `skill-lifecycle` |
| Runtime, container, deployment, PatchMon | 30 | `runtime-operations` |
| LLM, provider, agent, owner control | 29 | `sovereign-preflight`, `mcp-governance` |
| Database, vector, queue, backup | 20 | `data-integrity` |
| Determinism and evidence | 15 | `deterministic-assurance` |
| Security, compliance, supply chain | 13 | `security-supply-chain` |
| Android | 9 | `repository-evidence`, `runtime-operations` |
| Documents | 4 | `repository-evidence` |
| Cross-cutting/other | 27 | Selected by live capability routing |

## Deliberate non-migration

The following production surfaces are not copied or modified:

- MCP Python implementation and launcher.
- Dockerfile, Compose, workflow, image, registry, VPS, reverse proxy, or systemd configuration.
- Backend adapters, databases, migrations, queues, provider routes, secrets, or owner-protected values.
- Live hooks or shell commands.

The package is a guidance and discovery adapter. It must never be cited as evidence that a tool is reachable, authorized, healthy, deployed, or safe to execute.
