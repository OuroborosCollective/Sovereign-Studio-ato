# Google Stitch MCP bridge

## Purpose

Sovereign exposes a guarded bridge to Google's official Stitch remote MCP endpoint:

- Endpoint: `https://stitch.googleapis.com/mcp`
- Transport: streamable HTTP
- Upstream registry name: `com.googleapis.stitch/mcp`

The bridge deliberately does not hard-code upstream tool names. Google can add, rename, or remove remote MCP tools, so Sovereign reads the live `tools/list` catalog and hashes every observed contract before an action is called.

## Sovereign tools

- `stitch_mcp_status`: verifies the live catalog and reports configuration without returning credentials.
- `stitch_mcp_catalog`: returns current remote actions, annotations and optionally schemas.
- `stitch_mcp_call_read`: calls only actions that the upstream catalog explicitly marks `readOnlyHint=true`.
- `stitch_mcp_call_write`: calls non-read-only actions only when the server write switch and exact confirmation phrase are present.

## Authentication

Credentials must never be supplied in prompts or tool arguments. Configure exactly one protected file:

```bash
SOVEREIGN_STITCH_API_KEY_FILE=/opt/secure/stitch-api-key
# or
SOVEREIGN_STITCH_BEARER_TOKEN_FILE=/opt/secure/stitch-oauth-bearer
```

Optional Google Cloud quota project:

```bash
SOVEREIGN_STITCH_GOOGLE_PROJECT=your-google-cloud-project
```

The API-key file is sent as `X-Goog-Api-Key`. The OAuth bearer file is sent as `Authorization: Bearer …`. Secret-shaped keys such as `access_token`, `password`, `authorization`, or `api_key` are rejected in Stitch action arguments.

Google documents the `https://www.googleapis.com/auth/aida` OAuth scope for Stitch. The Google Stitch API must be enabled in the selected Cloud project before OAuth use.

## Write gate

Writes remain disabled by default:

```bash
SOVEREIGN_STITCH_ENABLE_WRITES=1
```

Every write call additionally requires:

```text
STITCH_WRITE_APPROVED
```

This confirmation is not a credential. It is an execution guard. Actions marked read-only by Google cannot be routed through the write tool, and actions not explicitly marked read-only cannot be routed through the read tool.

## Endpoint policy

The official endpoint is fixed by default. A custom endpoint requires both an HTTPS URL and:

```bash
SOVEREIGN_STITCH_ALLOW_CUSTOM_ENDPOINT=1
SOVEREIGN_STITCH_MCP_URL=https://example.invalid/mcp
```

Do not enable this for ordinary Google Stitch use.

## Verification sequence

1. Store the API key or OAuth bearer in the protected server file.
2. Restart the Sovereign MCP service with the new environment variables.
3. Call `stitch_mcp_status`.
4. Call `stitch_mcp_catalog` and inspect the live tool contracts.
5. Run one upstream read-only action through `stitch_mcp_call_read`.
6. Enable writes only when a concrete Stitch project/design mutation is intended.

A code merge proves only that the bridge is installed. Live Stitch readiness requires runtime readback from the deployed container with configured Google credentials.
