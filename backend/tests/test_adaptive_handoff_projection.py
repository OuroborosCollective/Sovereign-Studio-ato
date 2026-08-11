from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_runtime import adaptive_handoff
from agent_runtime.universal_toolchain import build_agent_handoff_context


class _Registry:
    def list_tools(self):
        return [
            {
                "name": "file_read",
                "description": "Read repository files",
                "effect": "read",
                "capabilities": ["filesystem", "repository"],
            },
            {
                "name": "file_write",
                "description": "Write repository files",
                "effect": "workspace-write",
                "capabilities": ["filesystem", "repository"],
            },
            {
                "name": "git_diff",
                "description": "Read repository diff",
                "effect": "read",
                "capabilities": ["git", "repository"],
            },
        ]


def test_read_only_projection_never_surfaces_mutating_tool(monkeypatch) -> None:
    monkeypatch.setattr(adaptive_handoff, "get_tool_registry", lambda: _Registry())
    result = adaptive_handoff.project_tools_for_mission("Analyse the repository diff and explain the files")
    selected = {item["name"] for item in result["selected"]}
    assert "file_read" in selected
    assert "git_diff" in selected
    assert "file_write" not in selected
    assert result["authorizesExecution"] is False
    assert result["mutationIntentDetected"] is False


def test_mutation_projection_is_advisory_and_bounded(monkeypatch) -> None:
    monkeypatch.setattr(adaptive_handoff, "get_tool_registry", lambda: _Registry())
    result = adaptive_handoff.project_tools_for_mission("Patch the repository file and create a draft PR", limit=99)
    assert result["limit"] == adaptive_handoff.MAX_PROJECTED_TOOLS
    assert result["mutationIntentDetected"] is True
    assert result["authorizesExecution"] is False
    assert len(result["selected"]) <= adaptive_handoff.MAX_PROJECTED_TOOLS


def test_provider_projection_keeps_retired_litellm_prohibited() -> None:
    provider = adaptive_handoff.provider_readiness_projection()
    assert provider["canonicalRoutes"] == {
        "paid": ["openrouter"],
        "free": ["freellm", "revolver"],
    }
    assert provider["prohibitedRuntimeRoutes"] == ["litellm"]
    assert provider["runtimeVerified"] is False


def test_universal_handoff_embeds_advisory_projection(monkeypatch) -> None:
    monkeypatch.setattr(adaptive_handoff, "get_tool_registry", lambda: _Registry())
    context = build_agent_handoff_context("Analyse repository status")
    assert "adaptiveHandoff" in context["diagnosis"]
    assert "[Adaptive evidence-bounded handoff projection]" in context["mission"]
    assert "paid=OpenRouter; free=FreeLLM/Revolver" in context["mission"]


def test_adaptive_handoff_and_universal_toolchain_mirrors_match() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for relative in (
        "agent_runtime/adaptive_handoff.py",
        "agent_runtime/universal_toolchain.py",
    ):
        canonical = repo_root / "backend" / relative
        mirror = repo_root / "scripts/sovereign-backend" / relative
        assert canonical.read_bytes() == mirror.read_bytes()
