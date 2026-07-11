# Sovereign ChatGPT Operator – Live setup

The operator code is already on `main`. This follow-up adds the official OpenAI Secure MCP Tunnel so the private VPS service can be used from ChatGPT without opening an inbound port.

## Values required once

Create these outside the repository and never paste them into issues, commits, logs, or chat:

1. A fine-grained GitHub token limited to `OuroborosCollective/Sovereign-Studio-ato` with Contents read/write and Pull requests read/write.
2. An OpenAI Secure MCP Tunnel ID from Platform tunnel settings.
3. A runtime API key for `tunnel-client` with tunnel use permission.

## VPS files

Create these two root-only files:

```text
/opt/sovereign-chatgpt-tools/.env
/opt/sovereign-chatgpt-tools/tunnel.env
```

Start from `.env.example` and `.tunnel.env.example`. Keep both files at mode `0600`.

The first installation may set:

```dotenv
SOVEREIGN_MCP_BOOTSTRAP_DATABASE=1
```

This creates or updates the read-only production role and the separate migration-preview database. The installer resets the switch to `0` afterward.

Safe initial production gates:

```dotenv
SOVEREIGN_MCP_ENABLE_DB_WRITES=0
SOVEREIGN_MCP_ENABLE_DEPLOY=0
SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS=0
SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS=0
```

For ongoing development of the project's own knowledge and vector database, this limited persistent mode is supported:

```dotenv
SOVEREIGN_MCP_ENABLE_DB_WRITES=1
SOVEREIGN_MCP_ENABLE_DEPLOY=1
SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS=1
SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS=0
```

This does not provide a generic SQL console. Every production migration still requires an isolated repository workspace, an exact SHA-256 confirmation, a successful rollback preview in the MCP runtime, and a second independent rollback preview in the root-separated host broker.

## Install on the VPS

From a current repository checkout:

```bash
cd /opt/sovereign-studio/tools/sovereign-chatgpt-mcp
sudo bash deploy/install-on-vps.sh
```

The installer:

- builds the unprivileged MCP container;
- creates the fixed-action Docker and migration broker;
- creates limited PostgreSQL identities when requested;
- keeps the production reader identity inside the MCP container;
- gives only the root-separated broker access to the existing backend admin environment path;
- downloads the latest official `openai/tunnel-client` Linux release;
- verifies the published SHA-256 checksum;
- configures the loopback MCP endpoint;
- runs `tunnel-client doctor`;
- starts both systemd services.

## Verify

```bash
sudo systemctl status sovereign-chatgpt-broker --no-pager
sudo systemctl status sovereign-openai-tunnel --no-pager
sudo docker inspect sovereign-chatgpt-mcp --format '{{json .State}}'
sudo -u sovereign-tunnel env \
  HOME=/var/lib/sovereign-tunnel \
  CONTROL_PLANE_API_KEY="$(sudo sed -n 's/^CONTROL_PLANE_API_KEY=//p' /opt/sovereign-chatgpt-tools/tunnel.env)" \
  /usr/local/bin/tunnel-client doctor --profile sovereign-chatgpt --explain
```

Do not print the environment files themselves.

Verify the active policy values without displaying passwords:

```bash
grep -E '^(SOVEREIGN_MCP_ENABLE_DB_WRITES|SOVEREIGN_MCP_ENABLE_DEPLOY|SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS|SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS)=' \
  /opt/sovereign-chatgpt-tools/.env
```

## Connect in ChatGPT

1. Open ChatGPT on the web.
2. Open **Settings → Security and login** and enable **Developer mode**.
3. Open **Settings → Plugins**.
4. Select the plus button to create a developer-mode app.
5. Choose **Tunnel** as the connection type.
6. Select the configured tunnel or paste its `tunnel_id`.
7. Name the app **Sovereign Operator**.
8. Use this description:

```text
Safely inspect and modify OuroborosCollective/Sovereign-Studio-ato. Use isolated workspaces, exact patches, targeted tests and Draft PRs. Never push directly to main or merge. Runtime, Docker, PostgreSQL and vector results must come from real evidence.
```

9. Create the app and confirm the advertised tool list.
10. Start a new chat, press **+ → More**, and select **Sovereign Operator**.

Once linked on the web, the app is also available in ChatGPT mobile.

## First prompts

```text
Use Sovereign Operator. Inspect the current repository and report the real backend and MCP runtime status. Do not change anything.
```

```text
Use Sovereign Operator. Find the cause of this backend error, create an isolated workspace, apply the smallest exact patch, run a targeted pytest and create only a Draft PR.
```

```text
Use Sovereign Operator. Add a new mobile-friendly menu to the existing navigation without replacing large files. Run targeted Vitest, typecheck, audit and build, then create only a Draft PR.
```

Write actions should remain confirmation-gated in ChatGPT. Recommended app permission: **Ask before making changes**.
