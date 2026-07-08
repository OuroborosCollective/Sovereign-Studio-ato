"""Tests for Agent Tool Creator.

Verifies dynamic tool creation, JSON schema generation, and execution.
"""

import pytest
from unittest.mock import MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent_runtime.agent_tool_creator import (
    AgentToolCreator,
    ToolSpec,
    ToolCreationError,
    agent_tool,
    register_example_tools,
    get_tool_creator,
    ReActAgent,
)


class TestAgentToolCreator:
    """Test AgentToolCreator functionality."""

    def test_initialization(self):
        """Should initialize with empty registry."""
        creator = AgentToolCreator()
        assert len(creator.list_tools()) == 0
        assert creator.workspace_path is None

    def test_initialization_with_workspace(self):
        """Should accept workspace path."""
        creator = AgentToolCreator("/tmp/workspace")
        assert creator.workspace_path == "/tmp/workspace"

    def test_register_function(self):
        """Should register a Python function as tool."""
        creator = AgentToolCreator()

        def my_tool(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        spec = creator.register_function(my_tool)

        assert spec.name == "my_tool"
        assert spec.description == "Add two numbers."
        assert spec.required == ["a", "b"]

    def test_register_with_custom_name(self):
        """Should accept custom tool name."""
        creator = AgentToolCreator()

        def my_function(x: str) -> str:
            """Process string."""
            return x.upper()

        spec = creator.register_function(my_function, name="custom_name")

        assert spec.name == "custom_name"
        assert "custom_name" in creator.list_tools()[0]["name"]

    def test_register_duplicate_raises(self):
        """Should raise on duplicate registration."""
        creator = AgentToolCreator()

        def tool1():
            pass

        creator.register_function(tool1, name="duplicate")
        with pytest.raises(ToolCreationError, match="existiert bereits"):
            creator.register_function(tool1, name="duplicate")

    def test_register_decorator(self):
        """Should work as decorator."""
        creator = AgentToolCreator()

        @creator.create_decorator(description="Test tool")
        def decorated_tool(x: int) -> int:
            """A decorated tool."""
            return x * 2

        tools = creator.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "decorated_tool"

    def test_workspace_required_flag(self):
        """Should respect workspace_required flag."""
        creator = AgentToolCreator()

        def workspace_tool(path: str) -> str:
            return path

        spec = creator.register_function(workspace_tool, workspace_required=True)
        assert spec.workspace_required is True


class TestToolExecution:
    """Test tool execution."""

    def test_execute_simple_function(self):
        """Should execute simple function."""
        creator = AgentToolCreator()

        def add(a: int, b: int) -> int:
            return a + b

        creator.register_function(add)

        result = creator.execute_tool("add", {"a": 5, "b": 3})

        assert result.is_ok()
        assert result.output == "8"

    def test_execute_with_default_parameter(self):
        """Should use default parameter if not provided."""
        creator = AgentToolCreator()

        def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}!"

        creator.register_function(greet)

        result = creator.execute_tool("greet", {"name": "World"})

        assert result.is_ok()
        assert "Hello" in result.output
        assert "World" in result.output

    def test_execute_missing_parameter(self):
        """Should block on missing required parameter."""
        creator = AgentToolCreator()

        def require_params(a: int, b: int) -> int:
            return a + b

        creator.register_function(require_params)

        result = creator.execute_tool("require_params", {"a": 5})

        assert result.is_blocked()
        assert "fehlender" in result.blocker.lower() or "missing" in result.blocker.lower()

    def test_execute_unknown_tool(self):
        """Should error on unknown tool."""
        creator = AgentToolCreator()

        result = creator.execute_tool("nonexistent", {})

        assert result.is_error()
        assert "nicht gefunden" in result.error.lower()

    def test_execute_workspace_required(self):
        """Should require workspace for workspace_required tools."""
        creator = AgentToolCreator(workspace_path=None)

        def ws_tool(path: str) -> str:
            return path

        creator.register_function(ws_tool, workspace_required=True)

        result = creator.execute_tool("ws_tool", {"path": "test"})

        assert result.is_blocked()
        assert "workspace" in result.blocker.lower()


class TestJSONSchemaGeneration:
    """Test JSON schema generation."""

    def test_generate_json_schema(self):
        """Should generate valid OpenAI-style schema."""
        creator = AgentToolCreator()

        def complex_tool(a: int, b: str, c: float = 1.0) -> str:
            """A complex tool."""
            return f"{a} {b} {c}"

        creator.register_function(complex_tool)

        schema = creator.get_json_schema()

        assert len(schema) == 1
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "complex_tool"
        assert "parameters" in schema[0]["function"]

    def test_schema_parameters(self):
        """Should include correct parameter types."""
        creator = AgentToolCreator()

        def typed_tool(a: str, b: int, c: bool, d: list) -> str:
            return ""

        creator.register_function(typed_tool)
        schema = creator.get_json_schema()

        params = schema[0]["function"]["parameters"]["properties"]
        assert params["a"]["type"] == "string"
        assert params["b"]["type"] == "integer"
        assert params["c"]["type"] == "boolean"
        assert params["d"]["type"] == "array"

    def test_schema_required_fields(self):
        """Should list required parameters."""
        creator = AgentToolCreator()

        def required_tool(a: str, b: int, c: float = 1.0) -> str:
            return ""

        creator.register_function(required_tool)
        schema = creator.get_json_schema()

        required = schema[0]["function"]["parameters"]["required"]
        assert "a" in required
        assert "b" in required
        assert "c" not in required


class TestAgentToolDecorator:
    """Test the global agent_tool decorator."""

    def test_global_decorator(self):
        """Should register via global decorator."""
        creator = get_tool_creator()

        # Register a tool
        @agent_tool(name="decorated_global", description="Globally decorated tool")
        def global_decorated(x: int) -> int:
            """A globally decorated function."""
            return x + 1

        tools = creator.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "decorated_global" in tool_names


class TestExampleTools:
    """Test example tool registration."""

    def test_register_example_tools(self):
        """Should register example tools."""
        creator = AgentToolCreator()
        register_example_tools(creator)

        tools = creator.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "string_reverse" in tool_names
        assert "calculate" in tool_names
        assert "file_search" in tool_names

    def test_string_reverse(self):
        """Should reverse strings."""
        creator = AgentToolCreator()
        register_example_tools(creator)

        result = creator.execute_tool("string_reverse", {"text": "hello"})

        assert result.is_ok()
        assert result.output == "olleh"

    def test_calculate_operations(self):
        """Should perform calculations."""
        creator = AgentToolCreator()
        register_example_tools(creator)

        result = creator.execute_tool("calculate", {"a": 10, "b": 5, "operation": "add"})
        assert result.is_ok()
        assert result.output in ("15", "15.0")  # int or float depending on Python version

        result = creator.execute_tool("calculate", {"a": 10, "b": 5, "operation": "mul"})
        assert result.is_ok()
        assert result.output in ("50", "50.0")


class TestReActAgent:
    """Test ReAct agent."""

    def test_initialization(self):
        """Should initialize with tool creator."""
        creator = AgentToolCreator()
        register_example_tools(creator)

        agent = ReActAgent(tool_creator=creator)

        assert agent.tool_creator is creator

    def test_run_without_llm(self):
        """Should return error message without LLM."""
        creator = AgentToolCreator()
        agent = ReActAgent(tool_creator=creator)

        result = agent.run("What is 5 + 3?")

        assert "nicht konfiguriert" in result["final_answer"].lower()
        assert len(result["tool_calls"]) == 0


class TestExecutionLog:
    """Test execution logging."""

    def test_log_execution(self):
        """Should log tool executions."""
        creator = AgentToolCreator()

        def logged_tool(x: int) -> int:
            return x * 2

        creator.register_function(logged_tool)
        creator.execute_tool("logged_tool", {"x": 5})

        log = creator.get_execution_log()
        assert len(log) == 1
        assert log[0]["tool_name"] == "logged_tool"
        assert log[0]["status"] == "success"

    def test_clear_log(self):
        """Should clear execution log."""
        creator = AgentToolCreator()

        def logged_tool(x: int) -> int:
            return x * 2

        creator.register_function(logged_tool)
        creator.execute_tool("logged_tool", {"x": 5})
        creator.clear_log()

        assert len(creator.get_execution_log()) == 0


class TestListRemoveTools:
    """Test tool listing and removal."""

    def test_list_tools(self):
        """Should list all registered tools."""
        creator = AgentToolCreator()

        def tool1():
            pass

        def tool2():
            pass

        creator.register_function(tool1, name="tool1")
        creator.register_function(tool2, name="tool2")

        tools = creator.list_tools()
        assert len(tools) == 2

    def test_get_tool(self):
        """Should retrieve specific tool."""
        creator = AgentToolCreator()

        def my_tool():
            pass

        creator.register_function(my_tool, name="my_tool")
        spec = creator.get_tool("my_tool")

        assert spec is not None
        assert spec.name == "my_tool"

    def test_get_nonexistent_tool(self):
        """Should return None for unknown tool."""
        creator = AgentToolCreator()
        assert creator.get_tool("unknown") is None

    def test_remove_tool(self):
        """Should remove registered tool."""
        creator = AgentToolCreator()

        def removable():
            pass

        creator.register_function(removable, name="removable")
        assert creator.remove_tool("removable") is True
        assert len(creator.list_tools()) == 0

    def test_remove_nonexistent_tool(self):
        """Should return False for unknown tool."""
        creator = AgentToolCreator()
        assert creator.remove_tool("unknown") is False
