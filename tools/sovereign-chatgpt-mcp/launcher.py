from __future__ import annotations

import android_validation_router
import repository_skill_tools
import server
import tool_extensions


android_validation_router.install(server.android, server.runtime, server.broker)
tool_extensions.register(server.mcp, server.broker)
repository_skill_tools.register(server.mcp, server.runtime)
mcp = server.mcp


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
