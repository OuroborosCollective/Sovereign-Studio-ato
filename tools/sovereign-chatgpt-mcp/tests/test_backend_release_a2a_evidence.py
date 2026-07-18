from __future__ import annotations

import server


def test_deploy_backend_requires_successful_a2a_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        server.broker,
        "call",
        lambda action, arguments, timeout: {
            "ok": True,
            "status": "DEPLOYED",
            "revision": arguments["expected_revision"],
            "image_digest": arguments["image_digest"],
        },
    )
    monkeypatch.setattr(
        server.a2a_runtime,
        "live_canary",
        lambda expected_revision: {
            "ok": True,
            "status": "A2A_LIVE_CANARY_VERIFIED",
            "expectedRevision": expected_revision,
            "samePersistedRunVerified": True,
            "ownerScopeVerified": True,
            "protectedValuesReturned": False,
        },
    )

    result = server._deploy_backend_with_a2a_evidence(
        "sha256:" + "a" * 64,
        "b" * 40,
        "b" * 40,
    )

    assert result["ok"] is True
    assert result["status"] == "DEPLOYED_AND_A2A_VERIFIED"
    assert result["a2aCanary"]["samePersistedRunVerified"] is True


def test_deploy_failure_does_not_run_a2a_canary(monkeypatch) -> None:
    called = False

    def canary(expected_revision: str):
        nonlocal called
        called = True
        return {"ok": True, "expectedRevision": expected_revision}

    monkeypatch.setattr(
        server.broker,
        "call",
        lambda action, arguments, timeout: {
            "ok": False,
            "status": "FAILED",
            "failure_family": "DEPLOY_FAILED",
        },
    )
    monkeypatch.setattr(server.a2a_runtime, "live_canary", canary)

    result = server._deploy_backend_with_a2a_evidence(
        "sha256:" + "a" * 64,
        "b" * 40,
        "b" * 40,
    )

    assert result["ok"] is False
    assert called is False


def test_a2a_failure_keeps_deployment_truth_but_blocks_success(monkeypatch) -> None:
    monkeypatch.setattr(
        server.broker,
        "call",
        lambda action, arguments, timeout: {
            "ok": True,
            "status": "DEPLOYED",
            "revision": arguments["expected_revision"],
        },
    )

    def fail_canary(expected_revision: str):
        raise RuntimeError(expected_revision)

    monkeypatch.setattr(server.a2a_runtime, "live_canary", fail_canary)

    result = server._deploy_backend_with_a2a_evidence(
        "sha256:" + "a" * 64,
        "b" * 40,
        "b" * 40,
    )

    assert result["ok"] is False
    assert result["status"] == "DEPLOYED_A2A_EVIDENCE_UNAVAILABLE"
    assert result["revision"] == "b" * 40
    assert result["a2aCanary"]["protectedValuesReturned"] is False
