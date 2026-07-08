"""Agent Tool Creator - Dynamische Tool-Erstellung für LLM-Agenten.

Dieses Modul ermöglicht es, Python-Funktionen automatisch als Tools
für LLM-Agenten zu registrieren. Es generiert JSON-Schemata und
führt Tools sicher im Workspace-Kontext aus.

Architektur:
┌─────────────────────────────────────────────────────────────┐
│                    Tool Decorator                          │
│  @tool(name="...", description="...", params={...})         │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Tool Registry                            │
│  - Python-Funktion → ToolSpec                             │
│  - JSON-Schema Generierung                                 │
│  - Parameter-Validierung                                   │
└──────────────────────────┬────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Tool Executor                            │
│  - Sichere Ausführung im Workspace-Kontext                 │
│  - Result-Normalisierung                                   │
│  - Event-Tracking                                         │
└─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import inspect
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, TypeVar, get_type_hints
from pathlib import Path

from .tools.base import ToolResult


# Type variable for generic function
F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ToolSpec:
    """Spezifikation eines dynamisch erstellten Tools."""
    name: str
    description: str
    function: Callable
    parameters: dict[str, Any]
    required: list[str] = field(default_factory=list)
    returns: dict[str, Any] | None = None
    workspace_required: bool = False
    examples: list[dict[str, str]] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))


@dataclass
class ToolCallRequest:
    """Anfrage für einen Tool-Aufruf."""
    tool_name: str
    parameters: dict[str, Any]
    call_id: str | None = None


class ToolCreationError(Exception):
    """Fehler bei der Tool-Erstellung."""


class ToolExecutionError(Exception):
    """Fehler bei der Tool-Ausführung."""


class AgentToolCreator:
    """Erstellt und verwaltet dynamische Tools für LLM-Agenten.

    Features:
    - Python-Funktionen als Tools registrieren
    - JSON-Schema für OpenAI/Claude API generieren
    - Parameter-Validierung
    - Workspace-Scoped Ausführung
    """

    def __init__(self, workspace_path: str | None = None):
        self.workspace_path = workspace_path
        self._tools: dict[str, ToolSpec] = {}
        self._execution_log: list[dict[str, Any]] = []

    def register_function(
        self,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        workspace_required: bool = False,
    ) -> ToolSpec:
        """Registriert eine Python-Funktion als Tool.

        Args:
            func: Die zu registrierende Funktion
            name: Optionaler Tool-Name (Standard: Funktionsname)
            description: Optionale Beschreibung
            workspace_required: Ob der Workspace-Pfad benötigt wird

        Returns:
            ToolSpec für das erstellte Tool
        """
        tool_name = name or func.__name__

        if tool_name in self._tools:
            raise ToolCreationError(f"Tool '{tool_name}' existiert bereits")

        # Parse Parameter aus Type-Hints und Docstring
        spec = self._create_tool_spec(
            func=func,
            name=tool_name,
            description=description,
            workspace_required=workspace_required,
        )

        self._tools[tool_name] = spec
        return spec

    def _create_tool_spec(
        self,
        func: Callable,
        name: str,
        description: str | None,
        workspace_required: bool,
    ) -> ToolSpec:
        """Erstellt eine ToolSpec aus einer Funktion."""
        sig = inspect.signature(func)
        hints = get_type_hints(func)

        parameters = {"type": "object", "properties": {}, "required": []}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            # Bestimme Parametertyp
            param_type = hints.get(param_name, str)
            json_type = self._python_type_to_json(param_type)

            param_spec = {
                "type": json_type,
                "description": self._extract_param_description(func, param_name),
            }

            # Default-Werte
            if param.default is not inspect.Parameter.empty:
                param_spec["default"] = param.default
            else:
                required.append(param_name)

            parameters["properties"][param_name] = param_spec

        parameters["required"] = required

        # Parse Return-Type
        return_hint = hints.get("return")
        returns = None
        if return_hint:
            returns = {"type": self._python_type_to_json(return_hint)}

        # Parse Beschreibung aus Docstring
        doc = description or (func.__doc__ or "").strip().split("\n")[0]

        return ToolSpec(
            name=name,
            description=doc,
            function=func,
            parameters=parameters,
            required=required,
            returns=returns,
            workspace_required=workspace_required,
        )

    def _python_type_to_json(self, py_type: Any) -> str:
        """Konvertiert Python-Typen zu JSON-Schema-Typen."""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
            Any: "any",
        }

        origin = getattr(py_type, "__origin__", None)
        if origin is list:
            return "array"
        if origin is dict:
            return "object"

        return type_map.get(py_type, "string")

    def _extract_param_description(self, func: Callable, param_name: str) -> str:
        """Extrahiert Parametern-Beschreibung aus Docstring."""
        doc = func.__doc__ or ""
        # Suche nach "Args:" Sektion
        args_match = re.search(rf"{param_name}\s*[:\-\s]+(.+?)(?:\n\s+\w|\n\n|$)", doc, re.DOTALL)
        if args_match:
            desc = args_match.group(1).strip()
            return desc.split("\n")[0][:200]
        return f"Parameter {param_name}"

    def create_decorator(
        self,
        name: str | None = None,
        description: str | None = None,
        workspace_required: bool = False,
    ) -> Callable[[F], F]:
        """Erstellt einen Dekorator für Tool-Registrierung.

        Beispiel:
            @tool_creator.create_decorator(name="mein_tool")
            def mein_tool(param1: str, param2: int) -> str:
                '''Mein Tool.'''
                return f"{param1} {param2}"
        """
        def decorator(func: F) -> F:
            spec = self.register_function(
                func=func,
                name=name,
                description=description,
                workspace_required=workspace_required,
            )
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator

    def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        workspace_path: str | None = None,
    ) -> ToolResult:
        """Führt ein Tool mit Parametern aus.

        Args:
            tool_name: Name des Tools
            parameters: Tool-Parameter
            workspace_path: Optionaler Workspace-Pfad

        Returns:
            ToolResult mit Ausführungsergebnis
        """
        if tool_name not in self._tools:
            return ToolResult(
                status="error",
                error=f"Tool '{tool_name}' nicht gefunden",
            )

        spec = self._tools[tool_name]

        # Validiere Parameter
        validation = self._validate_parameters(spec, parameters)
        if not validation["valid"]:
            return ToolResult(
                status="blocked",
                blocker=f"Parameter-Validierung fehlgeschlagen: {validation['error']}",
            )

        # Workspace-Prüfung
        if spec.workspace_required and not workspace_path:
            return ToolResult(
                status="blocked",
                blocker="Workspace-Pfad erforderlich für dieses Tool",
            )

        # Führe Funktion aus
        call_id = str(uuid.uuid4())[:8]
        start_time = datetime.now(timezone.utc)

        try:
            # Bereite Argumente vor
            kwargs = self._prepare_arguments(spec, parameters)

            # Füge Workspace hinzu wenn benötigt
            if spec.workspace_required and workspace_path:
                kwargs["workspace_path"] = workspace_path

            result = spec.function(**kwargs)

            # Log Ausführung
            self._log_execution(
                tool_name=tool_name,
                call_id=call_id,
                parameters=parameters,
                status="success",
                result=str(result)[:1000],
            )

            return ToolResult(
                status="done",
                output=str(result) if result is not None else "",
                metadata={
                    "tool_name": tool_name,
                    "call_id": call_id,
                    "execution_time_ms": self._ms_since(start_time),
                },
            )

        except TypeError as e:
            self._log_execution(tool_name, call_id, parameters, "error", str(e))
            return ToolResult(
                status="error",
                error=f"Parameter-Fehler: {e}",
            )
        except Exception as e:
            self._log_execution(tool_name, call_id, parameters, "error", str(e))
            return ToolResult(
                status="error",
                error=f"Ausführungsfehler: {e}",
            )

    def _validate_parameters(
        self,
        spec: ToolSpec,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Validiert Parameter gegen Tool-Spezifikation."""
        # Prüfe erforderliche Parameter
        for required in spec.required:
            if required not in parameters:
                return {"valid": False, "error": f"Fehlender Parameter: {required}"}

        # Prüfe Parametertypen
        for name, value in parameters.items():
            if name not in spec.parameters["properties"]:
                continue  # Erlaubter zusätzlicher Parameter

            param_spec = spec.parameters["properties"][name]
            expected_type = param_spec.get("type", "string")

            if not self._validate_type(value, expected_type):
                return {
                    "valid": False,
                    "error": f"Typ-Fehler für {name}: erwartet {expected_type}",
                }

        return {"valid": True}

    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Validiert einen Wert gegen erwarteten Typ."""
        type_checks = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "array": lambda v: isinstance(v, list),
            "object": lambda v: isinstance(v, dict),
        }

        checker = type_checks.get(expected_type)
        if checker:
            return checker(value)
        return True  # Unbekannte Typen durchlassen

    def _prepare_arguments(
        self,
        spec: ToolSpec,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Bereitet Funktionsargumente vor."""
        kwargs = {}
        for name, value in parameters.items():
            if name in spec.parameters["properties"]:
                kwargs[name] = value
        return kwargs

    def _log_execution(
        self,
        tool_name: str,
        call_id: str,
        parameters: dict[str, Any],
        status: str,
        result: str,
    ) -> None:
        """Loggt eine Tool-Ausführung."""
        self._execution_log.append({
            "tool_name": tool_name,
            "call_id": call_id,
            "parameters": parameters,
            "status": status,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def _ms_since(self, start: datetime) -> int:
        """Berechnet Millisekunden seit Start."""
        delta = datetime.now(timezone.utc) - start
        return int(delta.total_seconds() * 1000)

    def get_json_schema(self) -> list[dict[str, Any]]:
        """Generiert JSON-Schema für LLM-Tool-Aufrufe (OpenAI/Claude Format).

        Returns:
            Liste von Tool-Schemata im OpenAI function_calling Format
        """
        schemas = []
        for name, spec in self._tools.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            })
        return schemas

    def list_tools(self) -> list[dict[str, Any]]:
        """Liste alle registrierten Tools."""
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
                "required": spec.required,
                "workspace_required": spec.workspace_required,
            }
            for spec in self._tools.values()
        ]

    def get_tool(self, name: str) -> ToolSpec | None:
        """Holt ein Tool nach Namen."""
        return self._tools.get(name)

    def remove_tool(self, name: str) -> bool:
        """Entfernt ein Tool."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_execution_log(self) -> list[dict[str, Any]]:
        """Gibt das Ausführungslog zurück."""
        return list(self._execution_log)

    def clear_log(self) -> None:
        """Leert das Ausführungslog."""
        self._execution_log.clear()


# Globale Instanz
_tool_creator: AgentToolCreator | None = None


def get_tool_creator() -> AgentToolCreator:
    """Gibt die globale Tool-Creator Instanz zurück."""
    global _tool_creator
    if _tool_creator is None:
        _tool_creator = AgentToolCreator()
    return _tool_creator


# Convenience-Dekorator
def agent_tool(
    name: str | None = None,
    description: str | None = None,
    workspace_required: bool = False,
) -> Callable[[F], F]:
    """Dekorator um eine Funktion als Agent-Tool zu registrieren.

    Beispiel:
        @agent_tool(name="berechne", description="Führt eine Berechnung durch")
        def berechne(a: float, b: float, operation: str = "add") -> float:
            '''Berechnet a und b mit der gegebenen Operation.'''
            if operation == "add":
                return a + b
            elif operation == "sub":
                return a - b
            return 0

    Das Tool wird automatisch in der globalen Tool-Creator Instanz registriert.
    """
    creator = get_tool_creator()
    return creator.create_decorator(
        name=name,
        description=description,
        workspace_required=workspace_required,
    )


class ReActAgent:
    """ReAct (Reasoning + Acting) Agent für Tool-Ausführung.

    Führt einen einfachen Agenten-Loop aus:
    1. LLM fragt mit verfügbaren Tools
    2. Bei Tool-Aufruf: Tool ausführen
    3. Ergebnis an LLM zurückgeben
    4. Wiederholen bis finale Antwort
    """

    def __init__(
        self,
        llm_client: Any = None,
        tool_creator: AgentToolCreator | None = None,
    ):
        self.tool_creator = tool_creator or get_tool_creator()
        self.llm_client = llm_client

    def run(self, user_input: str, max_iterations: int = 10) -> dict[str, Any]:
        """Führt den Agenten-Loop aus.

        Args:
            user_input: Benutzer-Anfrage
            max_iterations: Maximale Iterationen

        Returns:
            Dict mit 'final_answer' und 'tool_calls'
        """
        messages = [{"role": "user", "content": user_input}]
        tool_calls = []
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            # LLM-Antwort mit Tools
            response = self._call_llm(messages)

            assistant_message = response.get("choices", [{}])[0].get("message", {})
            messages.append(assistant_message)

            # Tool-Aufrufe verarbeiten
            calls = assistant_message.get("tool_calls", [])
            if not calls:
                # Keine Tools mehr = fertig
                return {
                    "final_answer": assistant_message.get("content", ""),
                    "tool_calls": tool_calls,
                    "iterations": iterations,
                }

            # Tools ausführen
            for call in calls:
                func = call.get("function", {})
                tool_name = func.get("name", "")
                args = json.loads(func.get("arguments", "{}"))

                result = self.tool_creator.execute_tool(tool_name, args)

                tool_calls.append({
                    "tool": tool_name,
                    "args": args,
                    "result": result.output if result.is_ok() else result.error,
                    "status": result.status,
                })

                # Tool-Ergebnis als Nachricht hinzufügen
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", str(uuid.uuid4())),
                    "content": result.output or result.error or "",
                })

        return {
            "final_answer": "Maximale Iterationen erreicht",
            "tool_calls": tool_calls,
            "iterations": iterations,
        }

    def _call_llm(self, messages: list[dict]) -> dict[str, Any]:
        """Ruft das LLM auf (Stub - muss mit echtem Client implementiert werden)."""
        if not self.llm_client:
            # Mock-Antwort für Testing
            return {
                "choices": [{
                    "message": {
                        "content": "LLM Client nicht konfiguriert. Bitte implementieren Sie _call_llm().",
                        "tool_calls": [],
                    }
                }]
            }

        return self.llm_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=self.tool_creator.get_json_schema(),
            tool_choice="auto",
        )


# Vordefinierte Beispiel-Tools
def register_example_tools(creator: AgentToolCreator | None = None) -> AgentToolCreator:
    """Registriert Beispiel-Tools für Tests.

    Beispiel-Tools:
    - string_reverse: Kehrt einen String um
    - calculate: Führt mathematische Berechnungen durch
    - file_search: Sucht nach Dateien im Workspace
    """
    creator = creator or get_tool_creator()

    @creator.create_decorator(name="string_reverse", description="Kehrt die Buchstabenreihenfolge eines Strings um")
    def string_reverse(text: str) -> str:
        """Kehrt einen String um."""
        return text[::-1]

    @creator.create_decorator(name="calculate", description="Führt mathematische Berechnungen durch")
    def calculate(a: float, b: float, operation: str = "add") -> float:
        """Berechnet a und b mit der gegebenen Operation.

        Args:
            a: Erste Zahl
            b: Zweite Zahl
            operation: Operation (add, sub, mul, div)
        """
        ops = {
            "add": lambda x, y: x + y,
            "sub": lambda x, y: x - y,
            "mul": lambda x, y: x * y,
            "div": lambda x, y: x / y if y != 0 else float('inf'),
        }
        op = ops.get(operation, ops["add"])
        return op(a, b)

    @creator.create_decorator(name="file_search", description="Sucht nach Dateien im Workspace", workspace_required=True)
    def file_search(pattern: str, workspace_path: str | None = None) -> str:
        """Sucht nach Dateien die einem Pattern entsprechen.

        Args:
            pattern: Glob-Pattern (z.B. "*.py", "**/*.txt")
            workspace_path: Pfad zum Workspace
        """
        if not workspace_path:
            return "Kein Workspace-Pfad angegeben"

        try:
            base = Path(workspace_path)
            files = list(base.glob(pattern))
            return "\n".join([f.name for f in files]) if files else "Keine Dateien gefunden"
        except Exception as e:
            return f"Fehler bei der Suche: {e}"

    return creator
