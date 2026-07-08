"""Tests for MCP self-integration.

Verifies MCP server discovery, connection, and tool execution.
"""

import pytest
from unittest.mock import MagicMock, patch
import json

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent_runtime.mcp_integration import (
    MCPSelfIntegration,
    MCPServerConfig,
    MCPConnectionState,
    MCPToolSpec,
    MCPToolAdapter,
    get_mcp_integration,
    load_mcp_config_from_env,
)


class TestMCPSelfIntegration:
    """Test MCP self-integration functionality."""

    def test_initialization(self):
        """Should initialize with empty state."""
        mcp = MCPSelfIntegration()
        assert mcp.is_enabled() is False
        assert len(mcp.list_servers()) == 0

    def test_register_server(self):
        """Should register MCP server configuration."""
        mcp = MCPSelfIntegration()
        config = MCPServerConfig(
            name="test-server",
            command="npx",
            args=["-y", "@test/mcp-server"],
        )

        mcp.register_server(config)
        servers = mcp.list_servers()

        assert len(servers) == 1
        assert servers[0]["name"] == "test-server"
        assert servers[0]["registered"] is True

    def test_register_duplicate_raises(self):
        """Should raise on duplicate server registration."""
        mcp = MCPSelfIntegration()
        config = MCPServerConfig(name="test", command="test")

        mcp.register_server(config)
        with pytest.raises(ValueError, match="already registered"):
            mcp.register_server(config)

    def test_unregister_server(self):
        """Should unregister and disconnect server."""
        mcp = MCPSelfIntegration()
        config = MCPServerConfig(name="test", command="test")

        mcp.register_server(config)
        assert mcp.unregister_server("test") is True
        assert len(mcp.list_servers()) == 0

    def test_unregister_unknown_returns_false(self):
        """Should return False for unknown server."""
        mcp = MCPSelfIntegration()
        assert mcp.unregister_server("unknown") is False

    def test_enable_disable(self):
        """Should enable and disable MCP integration."""
        mcp = MCPSelfIntegration()
        assert mcp.is_enabled() is False

        mcp.enable()
        assert mcp.is_enabled() is True

        mcp.disable()
        assert mcp.is_enabled() is False

    def test_list_tools_empty(self):
        """Should return empty list when no servers connected."""
        mcp = MCPSelfIntegration()
        assert mcp.list_tools() == []

    def test_list_tools_server_filter(self):
        """Should filter tools by server name."""
        mcp = MCPSelfIntegration()
        # Mock connection state
        mcp._connections["server1"] = MagicMock()
        mcp._connections["server1"].state = MCPConnectionState.CONNECTED
        mcp._connections["server1"].tools = [
            MCPToolSpec("tool1", "desc1", {}, "server1"),
        ]
        mcp._connections["server2"] = MagicMock()
        mcp._connections["server2"].state = MCPConnectionState.CONNECTED
        mcp._connections["server2"].tools = [
            MCPToolSpec("tool2", "desc2", {}, "server2"),
        ]

        tools = mcp.list_tools("server1")
        assert len(tools) == 1
        assert tools[0].name == "tool1"

    def test_get_status(self):
        """Should return comprehensive status."""
        mcp = MCPSelfIntegration()
        mcp.enable()

        config = MCPServerConfig(name="test", command="test")
        mcp.register_server(config)

        status = mcp.get_status()
        assert status["enabled"] is True
        assert status["registered_servers"] == 1
        assert status["connected_servers"] == 0


class TestMCPServerConfig:
    """Test MCP server configuration."""

    def test_default_values(self):
        """Should have correct defaults."""
        config = MCPServerConfig(name="test", command="cmd")

        assert config.args == []
        assert config.env == {}
        assert config.url is None
        assert config.stdio is True
        assert config.auto_connect is False
        assert config.allowed_tools == []
        assert config.forbidden_tools == []


class TestMCPToolSpec:
    """Test MCP tool specification."""

    def test_creation(self):
        """Should create tool spec with required fields."""
        spec = MCPToolSpec(
            name="test_tool",
            description="Test tool description",
            input_schema={"type": "object"},
            server_name="test_server",
        )

        assert spec.name == "test_tool"
        assert spec.description == "Test tool description"
        assert spec.input_schema == {"type": "object"}
        assert spec.server_name == "test_server"


class TestMCPToolAdapter:
    """Test MCP tool adapter."""

    def test_initialization(self):
        """Should initialize with MCP integration."""
        mcp = MCPSelfIntegration()
        adapter = MCPToolAdapter(mcp)

        assert adapter.name == "mcp_tool"
        assert adapter.mcp is mcp

    def test_execute_blocks_when_disabled(self):
        """Should block execution when MCP is disabled."""
        mcp = MCPSelfIntegration()
        adapter = MCPToolAdapter(mcp)

        result = adapter.execute({"tool": "test_tool"}, None)

        assert result.is_blocked()
        assert "not enabled" in result.blocker.lower()

    def test_execute_requires_tool_name(self):
        """Should require tool name parameter."""
        mcp = MCPSelfIntegration()
        mcp.enable()
        adapter = MCPToolAdapter(mcp)

        result = adapter.execute({}, None)

        assert result.is_blocked()
        assert "required" in result.blocker.lower()


class TestMCPEnvConfig:
    """Test MCP configuration from environment."""

    def test_parse_env_value(self):
        """Should parse MCP server config from env value."""
        os.environ["MCP_SERVER_test"] = "command:npx,args:-y|@test/server,auto_connect:true"

        configs = load_mcp_config_from_env()
        test_config = next((c for c in configs if c.name == "test"), None)

        assert test_config is not None
        assert test_config.command == "npx"
        assert test_config.args == ["-y", "@test/server"]
        assert test_config.auto_connect is True

        del os.environ["MCP_SERVER_test"]

    def test_parse_env_value_minimal(self):
        """Should parse minimal MCP server config."""
        os.environ["MCP_SERVER_minimal"] = "command:mock-server"

        configs = load_mcp_config_from_env()
        minimal = next((c for c in configs if c.name == "minimal"), None)

        assert minimal is not None
        assert minimal.command == "mock-server"
        assert minimal.args == []
        assert minimal.auto_connect is False

        del os.environ["MCP_SERVER_minimal"]

    def test_missing_command_returns_none(self):
        """Should return None if command is missing."""
        os.environ["MCP_SERVER_nocmd"] = "args:arg1"

        configs = load_mcp_config_from_env()
        nocmd = next((c for c in configs if c.name == "nocmd"), None)

        assert nocmd is None

        del os.environ["MCP_SERVER_nocmd"]


class TestParameterValidation:
    """Test parameter validation."""

    def test_validate_required_params(self):
        """Should validate required parameters."""
        mcp = MCPSelfIntegration()
        schema = {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"},
            },
        }

        # Missing required
        result = mcp._validate_parameters(schema, {"name": "test"})
        assert result["valid"] is False
        assert "age" in result["error"]

        # All required present
        result = mcp._validate_parameters(schema, {"name": "test", "age": 25})
        assert result["valid"] is True

    def test_validate_types(self):
        """Should validate parameter types."""
        mcp = MCPSelfIntegration()
        schema = {
            "type": "object",
            "properties": {
                "str_field": {"type": "string"},
                "num_field": {"type": "number"},
                "bool_field": {"type": "boolean"},
            },
        }

        # Valid types
        result = mcp._validate_parameters(schema, {
            "str_field": "test",
            "num_field": 42,
            "bool_field": True,
        })
        assert result["valid"] is True

        # Invalid type
        result = mcp._validate_parameters(schema, {"str_field": 123})
        assert result["valid"] is False
        assert "string" in result["error"]
