from __future__ import annotations

import server
import tool_extensions


tool_extensions.register(server.mcp, server.broker)
mcp = server.mcp


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
