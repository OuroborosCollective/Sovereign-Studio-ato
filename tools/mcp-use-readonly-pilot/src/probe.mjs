import { inventoryFingerprint, validateLoopbackTarget } from "./inventory.mjs";

async function main() {
  // Deliberately no network discovery, server creation, or tool invocation.
  const endpoint = validateLoopbackTarget(process.env.MCP_USE_READONLY_ENDPOINT);
  const { MCPClient } = await import("@mcp-use/client");
  const client = new MCPClient({ mcpServers: { observed: { url: endpoint } } });
  try {
    const connection = await client.connect("observed");
    const inventory = inventoryFingerprint(await connection.listTools());
    process.stdout.write(JSON.stringify({
      ...inventory,
      source: "MCP tools/list",
      scope: "loopback-only",
      protocolTransportConnected: true,
      productRuntimeVerified: false,
    }) + "\n");
  } finally {
    await client.close();
  }
}

main().catch(() => {
  // Never echo endpoint, remote metadata, credentials, SDK errors or stack traces.
  process.stderr.write("MCP_USE_READONLY_PROBE_FAILED\n");
  process.exitCode = 2;
});
