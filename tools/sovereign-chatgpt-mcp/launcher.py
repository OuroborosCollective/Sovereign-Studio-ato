from __future__ import annotations

import android_validation_router
import deterministic_architecture_tools
import enterprise_backend_tools
import freemium_product_architect_tools
import openai_project_access_tools
import operating_profile
import operational_assurance_tools
import output_contracts
import operational_governance_tools
import proven_learning_tools
import repository_skill_tools
import skill_supply_chain_tools
import toolchain_composition
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
operational_assurance_tools.register(server.mcp, server.runtime, server.database, server.broker)
proven_learning_tools.register(server.mcp, server.runtime, server.owner_input)
toolchain_composition.register(server.mcp)
operating_profile.register(server.mcp)
OUTPUT_CONTRACT_INSTALLATION = output_contracts.install_output_contracts(server.mcp)
OPERATING_PROFILE_ENFORCEMENT = operating_profile.install_enforcement(server.mcp)
mcp = server.mcp


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
