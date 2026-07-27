# Google Stitch MCP bridge memory

## Durable facts

- The official Google Stitch remote MCP registry identity is `com.googleapis.stitch/mcp`.
- The canonical endpoint is `https://stitch.googleapis.com/mcp` using streamable HTTP.
- Upstream tool names and schemas are not stable contracts. Always discover them through live `tools/list` and bind a call to the observed contract hash.
- Credentials belong in protected files on the Sovereign host. Never pass API keys, bearer tokens, OAuth client secrets, passwords, or authorization headers through a chat prompt or MCP action arguments.
- Google documents the `https://www.googleapis.com/auth/aida` OAuth scope for Stitch. A Stitch API key is also supported by Google's Stitch tooling flow.
- Read calls require the remote action to state `readOnlyHint=true`.
- Write calls require both `SOVEREIGN_STITCH_ENABLE_WRITES=1` and the exact execution confirmation `STITCH_WRITE_APPROVED`.
- Repository integration is not live-runtime proof. After deployment, verify `stitch_mcp_status`, inspect `stitch_mcp_catalog`, and execute a real read-only action.

## Project boundary

This bridge belongs to Sovereign Studio ATO. Areloria/WASD lore may be remembered as cross-project personal history, but it must not create runtime or architectural coupling between the repositories.
