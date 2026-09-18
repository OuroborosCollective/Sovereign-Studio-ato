from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "agent-zero-testfile-smoke.yml"
SPEC = ROOT / "tests" / "e2e" / "agent-zero-testfile-smoke.spec.ts"


def test_testfile_smoke_is_a_separate_sovereign_ui_lane() -> None:
    workflow = WORKFLOW.read_text("utf-8")

    assert "name: Agent Zero Testfile UI Smoke" in workflow
    assert "sovereign/chatgpt/agent-zero-testfile-smoke" in workflow
    assert "tests/e2e/agent-zero-testfile-smoke.spec.ts" in workflow
    assert "SOVEREIGN_E2E_LIVE: '1'" in workflow
    assert "SOVEREIGN_E2E_BACKEND_PROXY_TARGET: https://sovereign-backend.arelorian.de" in workflow
    assert "pnpm exec playwright test tests/e2e/agent-zero-testfile-smoke.spec.ts" in workflow
    assert "RUNTIME_READBACK_SSH_PRIVATE_KEY" not in workflow
    assert "ssh " not in workflow
    assert "draft-pr/create" not in workflow


def test_testfile_smoke_uses_frontend_repository_run_and_sovereign_workspace_readback() -> None:
    spec = SPEC.read_text("utf-8")

    assert "mission__textarea" in spec
    assert "builder__start-task" in spec
    assert "/api/user/agent/repository/run" in spec
    assert "/api/user/agent/jobs/" in spec
    assert "/tools/file" in spec
    assert "/tools/git-status" in spec
    assert "genau eine leere reguläre Datei mit dem Namen testfile" in spec
    assert "Verändere keine andere Datei" in spec
    assert "Erzeuge keinen Commit und keinen Pull Request" in spec
    assert "draftPrCreated: false" in spec
    assert "sovereignWorkspaceReadbackVerified: true" in spec
    assert "secretValuesReturned: false" in spec
