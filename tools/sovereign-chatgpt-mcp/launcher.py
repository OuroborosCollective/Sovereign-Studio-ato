from __future__ import annotations

import android_validation_router
import deterministic_architecture_tools
import openai_project_access_tools
import repository_skill_tools
import server
import tool_extensions


android_validation_router.install(server.android, server.runtime, server.broker)
deterministic_architecture_tools.register(server.mcp, server.runtime)
tool_extensions.register(server.mcp, server.broker)
repository_skill_tools.register(server.mcp, server.runtime, server.database)
openai_project_access_tools.register(server.mcp, server.broker, server.controller_runtime)
mcp = server.mcp


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
