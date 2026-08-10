# Sovereign Studio ATO Codespace

This development container is additive. It does not replace or reconfigure the production Flask backend, MCP control plane, deployment image, provider routing, database ownership, or runtime secrets.

## Runtime alignment

- Node.js 22, matching the repository and CI contract.
- pnpm 9.12.2, matching `package.json`.
- Python 3.11, matching the production backend image.
- Java 17, matching Android CI.
- Docker-in-Docker for isolated image/container tests.
- GitHub CLI for repository and workflow inspection.
- Chromium + Playwright dependencies for browser tests.

Python dependencies intentionally use two virtual environments because the backend and MCP test contracts require different pytest versions:

- `.venv-backend-tests` installs `backend/requirements-test.txt`.
- `.venv-mcp-tests` installs `tools/sovereign-chatgpt-mcp/requirements.txt`.

No credentials are stored in the devcontainer configuration. Use GitHub Codespaces secrets or explicitly supplied local environment variables for tests that require external authentication.

## Test profiles

```bash
bash .devcontainer/run-tests.sh smoke
bash .devcontainer/run-tests.sh agent
bash .devcontainer/run-tests.sh browser
bash .devcontainer/run-tests.sh full
```

`smoke` checks the Flask/backend Python runtime, bounded MCP contracts, and TypeScript type checking.

`agent` additionally runs the canonical backend agent-runtime tests, frontend agent-runtime tests, and MCP production-flow/registry-evidence contracts.

`browser` runs the repository Playwright suite.

`full` runs the agent profile, the repository `pnpm run verify` contract, and the complete MCP pytest suite. Passing local/Codespace tests is development evidence only; it does not prove production deployment or PatchMon/runtime parity.

The production Flask container remains `scripts/sovereign-backend/Dockerfile` and continues to expose port 8787. The Vite development server uses port 3000.
