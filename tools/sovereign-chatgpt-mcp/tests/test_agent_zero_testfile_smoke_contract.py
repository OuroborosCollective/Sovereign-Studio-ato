from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "sovereign-chatgpt-mcp" / "deploy" / "agent-zero-testfile-smoke.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "agent-zero-testfile-smoke.yml"


def test_testfile_smoke_script_is_shell_valid_and_bounded() -> None:
    parsed = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    source = SCRIPT.read_text("utf-8")

    assert parsed.returncode == 0, parsed.stderr
    assert 'HOST_ROOT="/opt/sovereign-agent-workspaces"' in source
    assert 'AGENT_ZERO_ROOT="/a0/sovereign-workspaces"' in source
    assert 'BACKEND_ROOT="/var/lib/sovereign-agent/workspaces"' in source
    assert "genau eine leere reguläre Datei" in source
    assert "mit dem Namen testfile" in source
    assert "Verändere keine andere Datei" in source
    assert 'test "$STATUS" = "?? testfile"' in source
    assert '"fileSizeBytes":0' in source
    assert '"secretValuesReturned":false' in source


def test_testfile_smoke_runs_only_on_main_when_its_diagnostic_files_change() -> None:
    workflow = WORKFLOW.read_text("utf-8")

    assert "branches: [main]" in workflow
    assert "agent-zero-testfile-smoke.sh" in workflow
    assert "agent-zero-testfile-smoke.yml" in workflow
    assert "production-runtime-readback" in workflow
    assert "SOVEREIGN_RUNTIME_READBACK_SSH_PRIVATE_KEY" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "SHA256:pskBohJoTx/V3iCPaD9m1sW1vchvhvGc89lKnX0RocQ" in workflow
