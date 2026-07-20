from __future__ import annotations

import android_validation_router
import deterministic_architecture_tools
import enterprise_backend_tools
import freemium_product_architect_tools
import openai_project_access_tools
import operational_governance_tools
import proven_learning_tools
import repository_skill_tools
import skill_supply_chain_tools
import server
import tool_extensions


android_validation_router.install(server.android, server.runtime, server.broker)
deterministic_architecture_tools.register(server.mcp, server.runtime)
enterprise_backend_tools.register(server.mcp, server.runtime, server.broker)
freemium_product_architect_tools.register(server.mcp)
tool_extensions.register(server.mcp, server.broker)
repository_skill_tools.register(server.mcp, server.runtime, server.database)
skill_supply_chain_tools.register(server.mcp, server.runtime)
openai_project_access_tools.register(server.mcp, server.broker, server.controller_runtime)
operational_governance_tools.register(server.mcp, server.runtime, server.database, server.broker)
proven_learning_tools.register(server.mcp, server.runtime, server.owner_input)
mcp = server.mcp


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
