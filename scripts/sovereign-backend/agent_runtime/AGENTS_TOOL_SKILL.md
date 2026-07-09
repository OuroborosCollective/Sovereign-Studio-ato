# Backend Agent Tool - Skill Guide

> **Für AI-Agenten**: Pattern für Tool-Erstellung im Backend Agent Runtime.

---

## 🎯 Ziel

Python-Funktionen als LLM-Tools verfügbar machen mit:
- `@agent_tool` Dekorator
- Type-Hint basierte Parameter
- Workspace-Scoped Ausführung
- ReAct Agent Loop

---

## 📦 Tool Creator Pattern

```python
# backend/agent_runtime/agent_tool_creator.py
from functools import wraps
from typing import Any, Callable

def agent_tool(
    name: str,
    description: str,
    param_schema: dict = None
):
    """Decorator to mark a function as an agent tool."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        # Metadata für Tool-Registry
        wrapper._tool_name = name
        wrapper._tool_description = description
        wrapper._tool_schema = param_schema or generate_schema(func)
        wrapper._is_agent_tool = True
        
        return wrapper
    return decorator

# Verwendung
@agent_tool(
    name="file_read",
    description="Read contents of a file from workspace"
)
def file_read(path: str, workspace_path: str = None) -> dict:
    """Read file and return content."""
    full_path = workspace_path + "/" + path if workspace_path else path
    with open(full_path, 'r') as f:
        return {"ok": True, "content": f.read(), "path": path}
```

---

## 🛠️ Tool Result Pattern

```python
# backend/agent_runtime/tools/base.py
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolResult:
    """Standardized tool result."""
    ok: bool
    output: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }
```

---

## 📝 Tool Implementation Template

```python
# backend/agent_runtime/tools/my_tool.py
from typing import Any
from dataclasses import dataclass

from .base import ToolResult, ToolRegistry

@dataclass
class MyTool:
    """Custom tool for agent runtime."""
    
    name: str = "my_tool"
    description: str = "Does something useful"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def execute(self, **params) -> ToolResult:
        """Execute the tool with given parameters."""
        try:
            # Validate parameters
            if not self._validate_params(params):
                return ToolResult(
                    ok=False,
                    error="Invalid parameters"
                )
            
            # Execute logic
            result = self._do_work(params)
            
            return ToolResult(
                ok=True,
                output=result,
                metadata={"params": params}
            )
            
        except Exception as e:
            return ToolResult(
                ok=False,
                error=str(e)
            )
    
    def _validate_params(self, params: dict) -> bool:
        """Validate parameters before execution."""
        required = ["param1"]
        return all(k in params for k in required)
    
    def _do_work(self, params: dict) -> str:
        """Actual tool logic."""
        return f"Result: {params.get('param1')}"


# Registry
ToolRegistry.register("my_tool", MyTool)
```

---

## 🧪 Test Pattern

```python
# backend/tests/test_agent_my_tool.py
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent_runtime.tools.my_tool import MyTool, ToolResult

class TestMyTool:
    """Test MyTool functionality."""
    
    def test_initialization(self):
        """Should initialize with workspace."""
        tool = MyTool("/workspace")
        assert tool.workspace_path == "/workspace"
    
    def test_success_case(self):
        """Should return success on valid input."""
        tool = MyTool("/workspace")
        result = tool.execute(param1="value")
        
        assert result.ok is True
        assert "value" in result.output
    
    def test_failure_case(self):
        """Should handle invalid input."""
        tool = MyTool("/workspace")
        result = tool.execute()  # Missing param1
        
        assert result.ok is False
        assert "Invalid parameters" in result.error
    
    def test_error_handling(self):
        """Should handle exceptions."""
        tool = MyTool("/nonexistent")
        result = tool.execute(param1="test")
        
        assert result.ok is False
        assert result.error  # Error message exists
```

---

## 🔧 ReAct Agent Pattern

```python
# backend/agent_runtime/agent_tool_creator.py
class ReActAgent:
    """Reasoning + Acting Agent."""
    
    def __init__(self, tools: list, llm_client=None):
        self.tools = {t.name: t for t in tools}
        self.llm_client = llm_client
        self.max_iterations = 10
    
    def run(self, task: str) -> dict:
        """Execute task using ReAct pattern."""
        context = []
        
        for i in range(self.max_iterations):
            # 1. Reason
            thought = self._reason(task, context)
            context.append(f"Thought: {thought}")
            
            # 2. Check if done
            if self._is_complete(thought):
                return {"ok": True, "result": thought, "steps": context}
            
            # 3. Act
            action, result = self._act(thought)
            context.append(f"Action: {action}")
            context.append(f"Observation: {result}")
        
        return {"ok": False, "error": "Max iterations reached", "steps": context}
    
    def _reason(self, task: str, context: list) -> str:
        """Generate reasoning using LLM or heuristic."""
        if self.llm_client:
            return self.llm_client.think(task, context)
        
        # Fallback: simple heuristic
        return f"Need to complete: {task}"
    
    def _act(self, thought: str) -> tuple[str, str]:
        """Execute action based on thought."""
        # Parse tool name and params from thought
        tool_name = self._extract_tool(thought)
        
        if tool_name in self.tools:
            tool = self.tools[tool_name]
            params = self._extract_params(thought)
            result = tool.execute(**params)
            return tool_name, str(result)
        
        return "none", "No action taken"
```

---

## 📋 Checklist

- [ ] `@agent_tool` Dekorator verwenden
- [ ] `ToolResult` für standardisierte Rückgabe
- [ ] Workspace-Pfad als Konstruktor-Parameter
- [ ] Parameter-Validierung
- [ ] Exception-Handling
- [ ] Unit-Tests schreiben
- [ ] In `ToolRegistry` registrieren

---

## 🔗 Referenzen

- `backend/agent_runtime/agent_tool_creator.py`
- `backend/agent_runtime/tools/base.py`
- `backend/agent_runtime/tools/file_tool.py`
- `backend/agent_runtime/tools/git_tool.py`
- `backend/agent_runtime/tools/shell_tool.py`

---

*Last Updated: 2026-07-08*
