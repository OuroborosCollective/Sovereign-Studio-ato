"""MCP Self-Integration for Sovereign Agent Runtime.

This module provides dynamic MCP (Model Context Protocol) tool loading
and integration. It allows the runtime to discover, connect, and execute
MCP tools from any configured MCP server at runtime.

Key features:
- Dynamic MCP server discovery and connection
- Tool registration from MCP servers
- Capability negotiation
- Resource management
- Security policy enforcement
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable
import tempfile
import os

from .tools.base import ToolBase, ToolResult, ToolPolicyError


class MCPConnectionState(Enum):
    """MCP server connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None  # For HTTP-based MCP servers
    stdio: bool = True  # Use stdio transport
    auto_connect: bool = False  # Connect on startup
    allowed_tools: list[str] = field(default_factory=list)  # Empty = all allowed
    forbidden_tools: list[str] = field(default_factory=list)  # Block specific tools


@dataclass
class MCPToolSpec:
    """Specification of an MCP tool."""
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


@dataclass
class MCPConnection:
    """Represents an active MCP server connection."""
    server_name: str
    state: MCPConnectionState
    tools: list[MCPToolSpec] = field(default_factory=list)
    connected_at: datetime | None = None
    last_error: str | None = None
    process: Any = None  # subprocess handle


class MCPSelfIntegration:
    """Self-integrating MCP tool system.

    This class manages MCP server connections and provides a unified
    interface for discovering and executing MCP tools.
    """

    def __init__(self, workspace_root: str | None = None):
        self.workspace_root = workspace_root
        self._servers: dict[str, MCPServerConfig] = {}
        self._connections: dict[str, MCPConnection] = {}
        self._tool_cache: dict[str, ToolBase] = {}
        self._enabled = False

    def register_server(self, config: MCPServerConfig) -> None:
        """Register an MCP server configuration."""
        if config.name in self._servers:
            raise ValueError(f"MCP server '{config.name}' already registered")
        self._servers[config.name] = config

    def unregister_server(self, name: str) -> bool:
        """Unregister an MCP server and disconnect if connected."""
        if name not in self._servers:
            return False
        self.disconnect(name)
        del self._servers[name]
        return True

    def list_servers(self) -> list[dict[str, Any]]:
        """List all registered MCP servers."""
        result = []
        for name, config in self._servers.items():
            conn = self._connections.get(name)
            result.append({
                "name": name,
                "command": config.command,
                "registered": True,
                "connected": conn.state == MCPConnectionState.CONNECTED if conn else False,
                "tool_count": len(conn.tools) if conn else 0,
            })
        return result

    def connect(self, server_name: str) -> MCPConnection:
        """Connect to an MCP server and discover its tools."""
        if server_name not in self._servers:
            raise ValueError(f"Unknown MCP server: {server_name}")

        config = self._servers[server_name]

        # Initialize connection state
        conn = MCPConnection(
            server_name=server_name,
            state=MCPConnectionState.CONNECTING,
        )
        self._connections[server_name] = conn

        try:
            if config.stdio:
                # Start MCP server as subprocess with stdio
                env = os.environ.copy()
                env.update(config.env)

                process = subprocess.Popen(
                    [config.command] + config.args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    cwd=self.workspace_root,
                )

                # Send initialize request
                init_request = {
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {},
                            "resources": {},
                        },
                        "clientInfo": {
                            "name": "sovereign-agent-runtime",
                            "version": "1.0.0",
                        },
                    },
                }

                response = self._send_request(process, init_request)

                if "error" in response:
                    raise Exception(f"Initialize failed: {response['error']}")

                # Send tools/list request
                tools_request = {
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "method": "tools/list",
                    "params": {},
                }

                tools_response = self._send_request(process, tools_request)
                tools = tools_response.get("result", {}).get("tools", [])

                # Filter and register tools
                for tool in tools:
                    tool_name = tool.get("name", "")
                    if self._is_tool_allowed(config, tool_name):
                        conn.tools.append(MCPToolSpec(
                            name=tool_name,
                            description=tool.get("description", ""),
                            input_schema=tool.get("inputSchema", {}),
                            server_name=server_name,
                        ))

                conn.process = process
                conn.state = MCPConnectionState.CONNECTED
                conn.connected_at = datetime.now(timezone.utc)

            elif config.url:
                # HTTP-based MCP server (future support)
                conn.state = MCPConnectionState.ERROR
                conn.last_error = "HTTP MCP servers not yet supported"

            return conn

        except Exception as e:
            conn.state = MCPConnectionState.ERROR
            conn.last_error = str(e)
            raise

    def _send_request(self, process: Any, request: dict[str, Any]) -> dict[str, Any]:
        """Send JSON-RPC request to MCP server via stdio."""
        request_str = json.dumps(request) + "\n"
        process.stdin.write(request_str.encode())
        process.stdin.flush()

        response_line = process.stdout.readline()
        if not response_line:
            stderr = process.stderr.read().decode()
            raise Exception(f"No response from MCP server: {stderr}")

        return json.loads(response_line)

    def _is_tool_allowed(self, config: MCPServerConfig, tool_name: str) -> bool:
        """Check if a tool is allowed by policy."""
        # Check forbidden list first
        if config.forbidden_tools and tool_name in config.forbidden_tools:
            return False
        # Check allowed list (if specified, only allow those)
        if config.allowed_tools and tool_name not in config.allowed_tools:
            return False
        return True

    def disconnect(self, server_name: str) -> bool:
        """Disconnect from an MCP server."""
        if server_name not in self._connections:
            return False

        conn = self._connections[server_name]
        if conn.process:
            conn.process.terminate()
            try:
                conn.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                conn.process.kill()
            conn.process = None

        conn.state = MCPConnectionState.DISCONNECTED
        return True

    def list_tools(self, server_name: str | None = None) -> list[MCPToolSpec]:
        """List available tools from MCP servers."""
        if server_name:
            conn = self._connections.get(server_name)
            if not conn or conn.state != MCPConnectionState.CONNECTED:
                return []
            return conn.tools

        # List tools from all connected servers
        all_tools = []
        for conn in self._connections.values():
            if conn.state == MCPConnectionState.CONNECTED:
                all_tools.extend(conn.tools)
        return all_tools

    def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        server_name: str | None = None,
    ) -> ToolResult:
        """Execute an MCP tool."""
        # Find the tool
        tool_spec = None
        conn = None

        if server_name:
            conn = self._connections.get(server_name)
            if not conn or conn.state != MCPConnectionState.CONNECTED:
                return ToolResult(
                    status="error",
                    error=f"MCP server '{server_name}' not connected",
                )
            for t in conn.tools:
                if t.name == tool_name:
                    tool_spec = t
                    break
        else:
            # Search all connected servers
            for name, c in self._connections.items():
                if c.state == MCPConnectionState.CONNECTED:
                    for t in c.tools:
                        if t.name == tool_name:
                            tool_spec = t
                            conn = c
                            break

        if not tool_spec:
            return ToolResult(
                status="error",
                error=f"MCP tool '{tool_name}' not found",
            )

        # Validate parameters against schema
        validation = self._validate_parameters(tool_spec.input_schema, parameters)
        if not validation["valid"]:
            return ToolResult(
                status="blocked",
                blocker=f"Parameter validation failed: {validation['error']}",
            )

        # Execute via MCP protocol
        try:
            request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": parameters,
                },
            }

            response = self._send_request(conn.process, request)

            if "error" in response:
                return ToolResult(
                    status="error",
                    error=f"MCP tool error: {response['error']}",
                )

            result = response.get("result", {})
            content = result.get("content", [])

            # Extract text content from MCP response format
            output = ""
            for item in content:
                if item.get("type") == "text":
                    output += item.get("text", "")

            is_error = result.get("isError", False)

            return ToolResult(
                status="error" if is_error else "done",
                output=output,
                metadata={
                    "mcp_server": server_name,
                    "tool_name": tool_name,
                    "call_id": request["id"],
                },
            )

        except Exception as e:
            return ToolResult(
                status="error",
                error=f"MCP tool execution failed: {e}",
            )

    def _validate_parameters(
        self,
        schema: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate parameters against input schema."""
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for req_param in required:
            if req_param not in parameters:
                return {"valid": False, "error": f"Missing required: {req_param}"}

        for param_name, param_value in parameters.items():
            if param_name not in properties:
                continue  # Allow extra properties

            param_schema = properties[param_name]
            param_type = param_schema.get("type")

            # Basic type validation
            if param_type == "string" and not isinstance(param_value, str):
                return {"valid": False, "error": f"{param_name} must be string"}
            elif param_type == "number" and not isinstance(param_value, (int, float)):
                return {"valid": False, "error": f"{param_name} must be number"}
            elif param_type == "boolean" and not isinstance(param_value, bool):
                return {"valid": False, "error": f"{param_name} must be boolean"}
            elif param_type == "array" and not isinstance(param_value, list):
                return {"valid": False, "error": f"{param_name} must be array"}
            elif param_type == "object" and not isinstance(param_value, dict):
                return {"valid": False, "error": f"{param_name} must be object"}

        return {"valid": True}

    def enable(self) -> None:
        """Enable MCP integration."""
        self._enabled = True

    def disable(self) -> None:
        """Disable MCP integration and disconnect all servers."""
        self._enabled = False
        for server_name in list(self._connections.keys()):
            self.disconnect(server_name)

    def is_enabled(self) -> bool:
        """Check if MCP integration is enabled."""
        return self._enabled

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive MCP integration status."""
        connected_servers = []
        total_tools = 0

        for name, conn in self._connections.items():
            if conn.state == MCPConnectionState.CONNECTED:
                connected_servers.append(name)
                total_tools += len(conn.tools)

        return {
            "enabled": self._enabled,
            "registered_servers": len(self._servers),
            "connected_servers": len(connected_servers),
            "servers": connected_servers,
            "total_tools": total_tools,
        }


class MCPToolAdapter(ToolBase):
    """Adapter to wrap an MCP tool as a Sovereign ToolBase tool."""

    name = "mcp_tool"
    description = "Execute an MCP (Model Context Protocol) tool"
    parameters = {
        "server": {
            "type": "string",
            "required": False,
            "description": "MCP server name (auto-detect if not specified)",
        },
        "tool": {
            "type": "string",
            "required": True,
            "description": "MCP tool name to execute",
        },
        "parameters": {
            "type": "object",
            "required": False,
            "description": "Tool-specific parameters",
        },
    }

    def __init__(self, mcp_integration: MCPSelfIntegration):
        self.mcp = mcp_integration
        self.name = "mcp_tool"
        self.description = "Execute an MCP (Model Context Protocol) tool"
        self.parameters = MCPToolAdapter.parameters.copy()

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        """Execute an MCP tool via the integration."""
        if not self.mcp.is_enabled():
            return ToolResult(
                status="blocked",
                blocker="MCP integration is not enabled",
            )

        tool_name = params.get("tool", "")
        server_name = params.get("server")
        tool_params = params.get("parameters", {})

        if not tool_name:
            return ToolResult(
                status="blocked",
                blocker="Tool name is required",
            )

        return self.mcp.execute_tool(tool_name, tool_params, server_name)


# Global MCP integration instance
_mcp_integration: MCPSelfIntegration | None = None


def get_mcp_integration() -> MCPSelfIntegration:
    """Get the global MCP integration instance."""
    global _mcp_integration
    if _mcp_integration is None:
        _mcp_integration = MCPSelfIntegration()
    return _mcp_integration


def load_mcp_config_from_env() -> list[MCPServerConfig]:
    """Load MCP server configurations from environment variables.

    Format:
    MCP_SERVER_<NAME>=command:<cmd>,args:<arg1,arg2>,auto_connect:<true|false>
    """
    configs = []
    for key, value in os.environ.items():
        if key.startswith("MCP_SERVER_"):
            server_name = key[11:].lower()
            config = _parse_mcp_env_value(server_name, value)
            if config:
                configs.append(config)
    return configs


def _parse_mcp_env_value(name: str, value: str) -> MCPServerConfig | None:
    """Parse MCP server configuration from environment value."""
    parts = {}
    for part in value.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            parts[k.strip()] = v.strip()

    command = parts.get("command")
    if not command:
        return None

    args = []
    if "args" in parts:
        args = [a.strip() for a in parts["args"].split("|") if a.strip()]

    auto_connect = parts.get("auto_connect", "").lower() == "true"

    return MCPServerConfig(
        name=name,
        command=command,
        args=args,
        auto_connect=auto_connect,
    )
