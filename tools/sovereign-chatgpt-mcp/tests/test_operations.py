from __future__ import annotations

import pytest

from operations import OperationsRuntime


DIGEST = "sha256:" + "a" * 64
REVISION = "b" * 40


def test_deploy_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_DEPLOY", raising=False)
    result = OperationsRuntime().deploy_verified_release(
        image_digest=DIGEST,
        expected_revision=REVISION,
        confirmation_revision=REVISION,
    )
    assert result["status"] == "BLOCKED"
    assert result["blocker"] == "Deploy-Writes sind nicht aktiviert"


def test_deploy_requires_exact_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "1")
    result = OperationsRuntime().deploy_verified_release(
        image_digest=DIGEST,
        expected_revision=REVISION,
        confirmation_revision="c" * 40,
    )
    assert result["status"] == "BLOCKED"
    assert "Bestätigung" in result["blocker"]


def test_invalid_digest_never_reaches_script(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "1")
    with pytest.raises(ValueError, match="image_digest"):
        OperationsRuntime().deploy_verified_release(
            image_digest="latest",
            expected_revision=REVISION,
            confirmation_revision=REVISION,
        )


def test_rollback_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_DEPLOY", raising=False)
    result = OperationsRuntime().rollback_release(
        target_image_digest=DIGEST,
        confirmation_digest=DIGEST,
    )
    assert result["status"] == "BLOCKED"
