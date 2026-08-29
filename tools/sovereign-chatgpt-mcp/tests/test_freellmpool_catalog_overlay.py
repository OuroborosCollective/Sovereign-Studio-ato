from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import tomllib


MCP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MCP_ROOT.parents[1]
TEMPLATE_ROOT = MCP_ROOT / "templates" / "sovereign-freellmpool"
ENTRYPOINT_PATH = TEMPLATE_ROOT / "freellmpool-entrypoint.py"
EVIDENCE_PATH = TEMPLATE_ROOT / "freellmpool-catalog-overlay.evidence.json"
IMAGE_LOCK_PATH = TEMPLATE_ROOT / "freellmpool-image.lock.json"
DEPLOY_PATH = MCP_ROOT / "deploy" / "deploy-sovereign-backend"


def _entrypoint_literals() -> dict[str, object]:
    tree = ast.parse(ENTRYPOINT_PATH.read_text("utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            values[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return values


def test_bounded_catalog_overlay_is_hash_bound_and_evidence_scoped() -> None:
    literals = _entrypoint_literals()
    overlay = str(literals["CATALOG_OVERLAY"])
    overlay_sha256 = str(literals["CATALOG_SHA256"])
    evidence = json.loads(EVIDENCE_PATH.read_text("utf-8"))
    image_lock = json.loads(IMAGE_LOCK_PATH.read_text("utf-8"))

    assert hashlib.sha256(overlay.encode("utf-8")).hexdigest() == overlay_sha256
    assert overlay_sha256 == evidence["overlaySha256"]
    assert evidence["runtimeImage"] == image_lock["image"]
    assert evidence["runtimeUpstreamRevision"] == image_lock["upstreamRevision"]
    assert evidence["minimumProductionReadyRoutesUnchanged"] == 7
    assert evidence["deployBootstrapRequestTimeoutSecondsUnchanged"] == 45
    assert evidence["secretValuesReturned"] is False

    providers = tomllib.loads(overlay)["provider"]
    by_id = {str(provider["id"]): provider for provider in providers}
    assert set(by_id) == {"pollinations", "llm7", "ovh", "kilo"}
    assert [model["name"] for model in by_id["llm7"]["models"]] == [
        "default",
        "fast",
        "codestral-latest",
    ]
    for provider_id in ("pollinations", "ovh", "kilo"):
        assert by_id[provider_id]["models"] == []

    admitted = {item["modelId"]: item for item in evidence["admittedModels"]}
    assert admitted["llm7/default"]["successfulCompletions"] == 3
    assert admitted["llm7/default"]["attempts"] == 3
    assert admitted["llm7/fast"]["successfulCompletions"] == 3
    assert admitted["llm7/fast"]["attempts"] == 3
    assert admitted["llm7/codestral-latest"]["confirmationCount"] == 2


def test_entrypoint_installs_overlay_fail_closed_without_persisting_it() -> None:
    source = ENTRYPOINT_PATH.read_text("utf-8")

    assert 'CATALOG_PATH = Path("/tmp/sovereign-freellmpool-providers.toml")' in source
    assert "os.O_EXCL" in source
    assert "os.O_NOFOLLOW" in source
    assert "0o400" in source
    assert "os.fsync(handle.fileno())" in source
    assert "freellmpool_catalog_overlay_hash_mismatch" in source
    assert "freellmpool_catalog_overlay_readback_mismatch" in source
    assert 'os.environ["FREELLMPOOL_CONFIG"] = str(CATALOG_PATH)' in source
    assert 'os.environ["SOVEREIGN_FREELLMPOOL_CATALOG_SHA256"] = CATALOG_SHA256' in source
    assert "/var/lib/freellmpool/sovereign-freellmpool-providers.toml" not in source


def test_overlay_fix_does_not_override_canonical_deploy_readiness_or_request_bound() -> None:
    deploy = DEPLOY_PATH.read_text("utf-8")

    assert 'minimum_ready_routes = int(provider_status.get("minimumReadyRoutes") or 0)' in deploy
    assert "minimum_ready_routes = 7" not in deploy
    assert '"minimumReadyRoutes": minimum_ready_routes' in deploy
    minimum_guard = "if len(verified_receipts) < minimum_ready_routes:"
    assert deploy.count(minimum_guard) >= 2
    assert deploy.rindex(minimum_guard) < deploy.index('"minimumReadySatisfied": True')
    assert 'payload={"maxModels": 20}' in deploy
    assert "timeout_seconds=45" in deploy
    assert "provider_request_timeout_or_network_error" in deploy
