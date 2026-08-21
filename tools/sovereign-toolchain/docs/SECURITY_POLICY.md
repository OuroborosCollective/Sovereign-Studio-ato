# Security Policy

## Hard rules

- Do not expose `GITHUB_TOKEN` to browsers, mobile apps, no-code client-side flows, LLM prompts, service environments, or runtime files.
- Use only per-operation GitHub App installation tokens minted from a root-only Systemd credential; never use a persistent GitHub PAT or `GITHUB_TOKEN` fallback.
- Set `ALLOWED_REPOS`.
- Keep `TOOLCHAIN_API_KEY` enabled for public REST deployments.
- Put the service behind TLS.
- Validate origins at your reverse proxy if exposing MCP/REST publicly.
- Use Draft PRs for write actions.
- Keep `confirm=true` behind a user-visible confirmation.

## Write paths

Allowed:

- GitHub Contents API update to a non-default branch
- Draft PR creation
- External patch worker call after confirmation

Not allowed by default:

- direct default branch write
- shell command execution from agent input
- arbitrary repository access outside `ALLOWED_REPOS`
