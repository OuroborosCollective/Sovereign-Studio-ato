from __future__ import annotations

import ast
from pathlib import Path
import subprocess


MCP_ROOT = Path(__file__).resolve().parents[1]


def test_backend_deploy_bootstraps_revision_bound_v3_chat_receipts_before_readiness() -> None:
    deploy_path = MCP_ROOT / "deploy" / "deploy-sovereign-backend"
    deploy = deploy_path.read_text("utf-8")

    syntax = subprocess.run(
        ["bash", "-n", str(deploy_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    canary_marker = (
        'docker exec -i "$CONTAINER" python3 - "$EXPECTED_REVISION" '
        '"$DIGEST" <<\'PY\'\n'
    )
    embedded_canary = deploy.split(canary_marker, 1)[1].split("\nPY\n)", 1)[0]
    ast.parse(embedded_canary)

    health_index = deploy.index('stage = "health"')
    bootstrap_index = deploy.index('stage = "freellm_bootstrap_status"')
    readiness_index = deploy.index('stage = "readiness"')
    assert health_index < bootstrap_index < readiness_index

    assert 'os.environ.get("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()' in deploy
    assert '"X-Sovereign-Owner-Request-Key": owner_request_key' in deploy
    assert '"/api/internal/llm/freellm/providers"' in deploy
    assert 'f"/api/internal/llm/freellm/providers/{encoded_source_id}/reconcile"' in deploy
    assert 'f"/api/internal/llm/freellm/providers/{encoded_source_id}/discover"' in deploy
    assert "minimum_ready_routes = 7" in deploy
    assert "if len(verified_receipts) < minimum_ready_routes:" in deploy
    assert '"minimumReadyRoutes": minimum_ready_routes' in deploy
    assert '"minimumReadySatisfied": len(verified_receipts) >= minimum_ready_routes' in deploy
    assert 'status_code not in {200, 409}' in deploy
    assert 'except urllib.error.HTTPError as exc:' in deploy
    assert 'timeout_seconds: int = 120' in deploy
    assert 'timeout_seconds=45' in deploy
    assert 'except (TimeoutError, urllib.error.URLError, OSError) as exc:' in deploy
    assert '"blocker": "provider_request_timeout_or_network_error"' in deploy

    assert 'receipt.get("schemaVersion") == "sovereign.freellm-route-receipt.v3"' in deploy
    assert 'receipt.get("generalChatEvidenceVerified") is True' in deploy
    assert 'runtime.get("sourceRevision") == expected_revision' in deploy
    assert 'runtime.get("imageDigest") == expected_digest' in deploy
    assert 'runtime.get("sourceRevisionVerified") is True' in deploy
    assert 'runtime.get("imageDigestVerified") is True' in deploy
    assert 'raise RuntimeError("no revision-bound FreeLLM v3 chat-evidence receipt became ready")' in deploy
    assert '"freellmBootstrap": freellm_bootstrap' in deploy
    assert '"protectedValuesReturned": False' in deploy

    # The owner bridge key is process-local and must never be emitted.
    assert 'print(owner_request_key)' not in deploy
    assert 'printf \'%s\' "$SOVEREIGN_OWNER_REQUEST_KEY"' not in deploy
