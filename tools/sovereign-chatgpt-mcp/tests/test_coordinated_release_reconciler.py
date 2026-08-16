from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
SCRIPT = ROOT / "deploy/reconcile-main-release.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("coordinated_release_reconciler", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_gate_accepts_only_exact_successful_revision(monkeypatch) -> None:
    module = _load()
    revision = "a" * 40
    monkeypatch.setattr(
        module,
        "_github_json",
        lambda _path: {
            "workflow_runs": [
                {
                    "id": 10,
                    "run_attempt": 1,
                    "head_sha": "b" * 40,
                    "status": "completed",
                    "conclusion": "success",
                },
                {
                    "id": 11,
                    "run_attempt": 1,
                    "head_sha": revision,
                    "status": "completed",
                    "conclusion": "failure",
                },
                {
                    "id": 12,
                    "run_attempt": 2,
                    "head_sha": revision,
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "https://github.test/run/12",
                },
            ]
        },
    )

    result = module._release_gate(revision)

    assert result["ready"] is True
    assert result["status"] == "RELEASE_GATE_VERIFIED"
    assert result["runId"] == 12
    assert result["headSha"] == revision


def test_waiting_release_gate_performs_no_image_or_runtime_mutation(monkeypatch, tmp_path) -> None:
    module = _load()
    revision = "c" * 40
    monkeypatch.setattr(module, "STATE_DIR", tmp_path)
    monkeypatch.setattr(module, "STATUS_FILE", tmp_path / "status.json")
    module.EXPECTED_REVISION = revision
    module.EXPECTED_RELEASE_GATE_RUN_ID = "77"
    module.EXPECTED_BACKEND_DIGEST = "sha256:" + "a" * 64
    module.EXPECTED_MCP_DIGEST = "sha256:" + "b" * 64
    module.EXPECTED_MANIFEST_EVIDENCE_SHA256 = "c" * 64
    monkeypatch.setattr(module, "_main_revision", lambda: revision)
    monkeypatch.setattr(
        module,
        "_release_gate",
        lambda _revision, **_kwargs: {"ready": False, "status": "WAITING_FOR_RELEASE_GATE", "runId": 77},
    )
    monkeypatch.setattr(
        module,
        "_image_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("image pull must not start")),
    )

    result = module.reconcile()

    assert result["status"] == "WAITING_FOR_RELEASE_GATE"
    assert result["mutationPerformed"] is False
    assert json.loads((tmp_path / "status.json").read_text("utf-8"))["revision"] == revision


def _scoped_reconcile_fixture(
    monkeypatch, tmp_path, *, restored: bool = True, backend_current: bool = False
):
    module = _load()
    revision = "d" * 40
    previous_revision = "a" * 40
    backend_digest = "sha256:" + "b" * 64
    mcp_digest = "sha256:" + "c" * 64
    previous_digest = "sha256:" + "e" * 64
    # Bind the backend env pointer the installer would have persisted. The
    # managed runtime.env stores only the sanctioned pointer; the real secret
    # backend env file is a separate regular file. Secret contents are never
    # read by the reconciler.
    backend_env_file = tmp_path / "backend.env"
    backend_env_file.write_text("SOVEREIGN_OWNER_REQUEST_KEY=not-a-secret-fixture\n", "utf-8")
    os.chmod(backend_env_file, 0o600)
    managed_env_file = tmp_path / "runtime.env"
    managed_env_file.write_text(
        f"SOVEREIGN_BACKEND_ENV_FILE={backend_env_file}\n",
        "utf-8",
    )
    os.chmod(managed_env_file, 0o600)
    monkeypatch.setattr(module, "MANAGED_RUNTIME_ENV", managed_env_file)
    # The sanctioned set is a production contract; in the test sandbox the
    # backend env file lives under tmp_path, so the membership check still runs
    # against a known allow-list rather than being bypassed.
    monkeypatch.setattr(
        module, "SANCTIONED_BACKEND_ENV_PATHS", frozenset({str(backend_env_file)})
    )
    scope = {
        "revision": revision,
        "releaseGateRunId": 91,
        "backendDigest": backend_digest,
        "mcpDigest": mcp_digest,
        "manifestEvidenceSha256": "f" * 64,
    }
    gate = {"ready": True, "status": "RELEASE_GATE_VERIFIED", "runId": 91}
    backend_image = {
        "repository": module.BACKEND_REPOSITORY,
        "revision": revision,
        "digest": backend_digest,
    }
    mcp_image = {
        "repository": module.MCP_REPOSITORY,
        "revision": revision,
        "digest": mcp_digest,
    }
    previous_backend = {
        "present": True,
        "valid": True,
        "container": "sovereign-backend",
        "containerId": "old-container",
        "running": True,
        "startedAt": "2026-08-14T18:00:00Z",
        "networks": ["areloria_arelorian-network", "sovereign-private", "supabase_default"],
        "revision": previous_revision,
        "digest": previous_digest,
    }
    if backend_current:
        previous_backend.update({"revision": revision, "digest": backend_digest})
    current_backend = {
        **previous_backend,
        "containerId": "restored-container",
        "startedAt": "2026-08-14T19:46:16Z",
    }
    if not restored:
        current_backend.update({"revision": revision, "digest": backend_digest})
    current_mcp = {
        "present": True,
        "valid": True,
        "container": "sovereign-chatgpt-mcp",
        "containerId": "old-mcp",
        "running": True,
        "health": "healthy",
        "startedAt": "2026-08-12T10:00:00Z",
        "networks": ["supabase_default"],
        "revision": previous_revision,
        "digest": "sha256:" + "1" * 64,
    }
    identity_calls = {"backend": 0}

    def container_identity(container, _repository):
        if container == "sovereign-backend":
            identity_calls["backend"] += 1
            return dict(previous_backend if identity_calls["backend"] == 1 else current_backend)
        return dict(current_mcp)

    monkeypatch.setattr(module, "STATE_DIR", tmp_path)
    monkeypatch.setattr(module, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(module, "_expected_scope", lambda: dict(scope))
    monkeypatch.setattr(module, "_main_revision", lambda: revision)
    monkeypatch.setattr(module, "_release_gate", lambda *_args, **_kwargs: dict(gate))
    monkeypatch.setattr(module, "_refresh_operator_source", lambda _scope: {"revision": revision})
    monkeypatch.setattr(
        module,
        "_image_evidence",
        lambda repository, _revision: dict(
            backend_image if repository == module.BACKEND_REPOSITORY else mcp_image
        ),
    )
    monkeypatch.setattr(module, "_container_identity", container_identity)
    monkeypatch.setattr(
        module,
        "_backend_health_identity",
        lambda: {
            "ok": True,
            "status": "VERIFIED",
            "sourceRevision": current_backend["revision"],
            "imageDigest": current_backend["digest"],
            "responseSha256": "2" * 64,
        },
    )
    return module, scope, previous_backend, current_backend


def test_backend_post_production_failure_preserves_scope_and_proves_restoration(
    monkeypatch, tmp_path
) -> None:
    module, scope, previous_backend, _current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path
    )
    mcp_calls: list[str] = []

    def failed_backend_command(_argv, **_kwargs):
        raise module.ReconcileError(
            "backend_deploy",
            "exit=1;outputSha256=" + "3" * 64,
            safe_evidence={
                "outputSha256": "3" * 64,
                "diagnostics": [
                    {"stage": "platform_integrations", "failureFamily": "RuntimeError"},
                    {"stage": "admin_canary", "failureFamily": "ContractFailure"},
                ],
            },
        )

    monkeypatch.setattr(module, "_command_json", failed_backend_command)
    monkeypatch.setattr(
        module,
        "_deploy_mcp_from_ci_scope",
        lambda *_args, **_kwargs: mcp_calls.append("called"),
    )

    result = module.reconcile()

    assert result["status"] == "BACKEND_DEPLOY_FAILED"
    assert result["revision"] == scope["revision"]
    assert result["expectedScope"] == scope
    assert result["previousBackend"] == previous_backend
    assert result["mutationEvidenceStatus"] == "PERFORMED"
    assert result["mutationPerformed"] is True
    assert result["restoration"]["identityRestored"] is True
    assert result["restoration"]["networkParity"] is True
    assert result["restoration"]["livenessParity"] is True
    assert result["restoration"]["containerRecreated"] is True
    assert result["retryable"] is False
    assert mcp_calls == []


@pytest.mark.parametrize(
    ("diagnostics", "expected_status", "expected_mutation"),
    [
        ([{"stage": "candidate_health", "failureFamily": "ContractFailure"}], "PERFORMED", True),
        ([{"stage": "preflight", "failureFamily": "ContractFailure"}], "UNKNOWN", None),
        ([], "UNKNOWN", None),
    ],
)
def test_backend_failure_records_proven_effects_and_never_encodes_unknown_as_false(
    monkeypatch, tmp_path, diagnostics, expected_status, expected_mutation
) -> None:
    module, _scope, _previous_backend, current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path
    )
    current_backend.update(
        {"containerId": "old-container", "startedAt": "2026-08-14T18:00:00Z"}
    )

    def failed_backend_command(_argv, **_kwargs):
        safe_evidence = {"outputSha256": "4" * 64}
        if diagnostics:
            safe_evidence["diagnostics"] = diagnostics
        raise module.ReconcileError(
            "backend_deploy",
            "exit=1;outputSha256=" + "4" * 64,
            safe_evidence=safe_evidence,
        )

    monkeypatch.setattr(module, "_command_json", failed_backend_command)

    result = module.reconcile()

    assert result["mutationEvidenceStatus"] == expected_status
    if expected_mutation is None:
        assert "mutationPerformed" not in result
    else:
        assert result["mutationPerformed"] is expected_mutation
    if diagnostics and diagnostics[0]["stage"] == "candidate_health":
        assert (
            result["restoration"]["status"]
            == "PREVIOUS_IDENTITY_NETWORK_AND_LIVENESS_UNCHANGED"
        )
        assert result["restoration"]["identityRestored"] is False
    assert result["retryable"] is False


def test_backend_post_production_failure_does_not_claim_mismatched_restore(
    monkeypatch, tmp_path
) -> None:
    module, _scope, _previous_backend, _current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path, restored=False
    )

    def failed_backend_command(_argv, **_kwargs):
        raise module.ReconcileError(
            "backend_deploy",
            "exit=1;outputSha256=" + "5" * 64,
            safe_evidence={
                "diagnostics": [{"stage": "production_health", "failureFamily": "ContractFailure"}]
            },
        )

    monkeypatch.setattr(module, "_command_json", failed_backend_command)

    result = module.reconcile()

    assert result["mutationPerformed"] is True
    assert (
        result["restoration"]["status"]
        == "RESTORATION_IDENTITY_NETWORK_OR_LIVENESS_UNVERIFIED"
    )
    assert result["restoration"]["identityRestored"] is False
    assert result["restoration"]["livenessParity"] is False


def test_backend_restore_requires_network_attachment_parity(monkeypatch, tmp_path) -> None:
    module, _scope, _previous_backend, current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path
    )
    current_backend["networks"] = ["supabase_default"]

    def failed_backend_command(_argv, **_kwargs):
        raise module.ReconcileError(
            "backend_deploy",
            "exit=1;outputSha256=" + "5" * 64,
            safe_evidence={
                "diagnostics": [{"stage": "admin_canary", "failureFamily": "ContractFailure"}]
            },
        )

    monkeypatch.setattr(module, "_command_json", failed_backend_command)

    result = module.reconcile()

    assert result["mutationPerformed"] is True
    assert result["restoration"]["identityParity"] is True
    assert result["restoration"]["livenessParity"] is True
    assert result["restoration"]["networkParity"] is False
    assert result["restoration"]["identityRestored"] is False
    assert (
        result["restoration"]["status"]
        == "RESTORATION_IDENTITY_NETWORK_OR_LIVENESS_UNVERIFIED"
    )


def test_restart_proves_mutation_without_claiming_container_recreation_or_restore() -> None:
    module = _load()
    revision = "a" * 40
    digest = "sha256:" + "b" * 64
    previous = {
        "present": True,
        "containerId": "same-container",
        "running": True,
        "startedAt": "2026-08-14T18:00:00Z",
        "networks": ["sovereign-private"],
        "revision": revision,
        "digest": digest,
    }
    current = {
        **previous,
        "startedAt": "2026-08-14T19:00:00Z",
    }
    health = {
        "ok": True,
        "sourceRevision": revision,
        "imageDigest": digest,
    }

    mutation_status, mutation_performed = module._production_mutation_evidence(
        [], previous, current
    )
    restoration = module._restoration_evidence(previous, current, health)

    assert mutation_status == "PERFORMED"
    assert mutation_performed is True
    assert restoration["containerRecreated"] is False
    assert restoration["containerRestarted"] is True
    assert restoration["identityRestored"] is False
    assert (
        restoration["status"]
        == "RESTARTED_IDENTITY_NETWORK_AND_LIVENESS_VERIFIED"
    )


def test_runtime_readback_failure_retains_successful_mutation_evidence(
    monkeypatch, tmp_path
) -> None:
    module, scope, _previous_backend, _current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        module,
        "_command_json",
        lambda *_args, **_kwargs: {"receipt": {"ok": True}, "outputSha256": "6" * 64},
    )
    monkeypatch.setattr(
        module,
        "_deploy_mcp_from_ci_scope",
        lambda *_args, **_kwargs: {"status": "DEPLOYED", "revision": scope["revision"]},
    )
    monkeypatch.setattr(
        module,
        "_runtime_readback",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            module.ReconcileError("runtime_readback", "broker is not ready")
        ),
    )

    result = module.reconcile()

    assert result["status"] == "RUNTIME_READBACK_FAILED"
    assert result["revision"] == scope["revision"]
    assert result["expectedScope"] == scope
    assert result["mutationEvidenceStatus"] == "PERFORMED"
    assert result["mutationPerformed"] is True
    assert result["retryable"] is False


def test_unexpected_runtime_readback_failure_stays_redacted_and_retains_mutation(
    monkeypatch, tmp_path
) -> None:
    module, scope, _previous_backend, _current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        module,
        "_command_json",
        lambda *_args, **_kwargs: {"receipt": {"ok": True}, "outputSha256": "6" * 64},
    )
    monkeypatch.setattr(
        module,
        "_deploy_mcp_from_ci_scope",
        lambda *_args, **_kwargs: {"status": "DEPLOYED", "revision": scope["revision"]},
    )
    raw_secret = "private-broker-error-detail"
    monkeypatch.setattr(
        module,
        "_runtime_readback",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(raw_secret)),
    )

    result = module.reconcile()

    assert result["status"] == "RUNTIME_READBACK_FAILED"
    assert result["mutationPerformed"] is True
    assert result["runtimeReadback"]["failureFamily"] == "OSError"
    assert raw_secret not in json.dumps(result)


@pytest.mark.parametrize(
    ("installer_stage", "expected_status", "expected_mutation"),
    [
        ("preflight", "UNKNOWN", None),
        ("backup_existing_control_plane", "UNKNOWN", None),
        ("replace_mcp_container", "PERFORMED", True),
    ],
)
def test_mcp_failure_uses_observed_effect_instead_of_desired_drift(
    monkeypatch, tmp_path, installer_stage, expected_status, expected_mutation
) -> None:
    module, scope, _previous_backend, _current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path, backend_current=True
    )

    def failed_mcp_update(*_args, **_kwargs):
        raise module.ReconcileError(
            "mcp_deploy",
            "exit=1;outputSha256=" + "7" * 64,
            safe_evidence={
                "outputSha256": "7" * 64,
                "installerDiagnostic": {
                    "stage": installer_stage,
                    "rollbackAttempted": installer_stage != "preflight",
                },
            },
        )

    monkeypatch.setattr(module, "_deploy_mcp_from_ci_scope", failed_mcp_update)

    result = module.reconcile()

    assert result["status"] == "MCP_UPDATE_FAILED"
    assert result["revision"] == scope["revision"]
    assert result["mutationEvidenceStatus"] == expected_status
    assert result["mcpUpdate"]["mutationEvidenceStatus"] == expected_status
    if expected_mutation is None:
        assert "mutationPerformed" not in result
        assert "mutationPerformed" not in result["mcpUpdate"]
    else:
        assert result["mutationPerformed"] is expected_mutation
        assert result["mcpUpdate"]["mutationPerformed"] is expected_mutation
    assert result["rollback"]["attempted"] is False
    assert result["retryable"] is False


def test_mcp_component_evidence_stays_unknown_when_only_backend_mutated(
    monkeypatch, tmp_path
) -> None:
    module, scope, _previous_backend, _current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path
    )
    command_calls: list[str] = []

    def successful_backend_command(argv, **_kwargs):
        command_calls.append(str(argv[0]))
        return {"receipt": {"ok": True}, "outputSha256": "8" * 64}

    def failed_mcp_preflight(*_args, **_kwargs):
        raise module.ReconcileError(
            "mcp_deploy",
            "exit=1;outputSha256=" + "9" * 64,
            safe_evidence={
                "outputSha256": "9" * 64,
                "installerDiagnostic": {
                    "stage": "preflight",
                    "rollbackAttempted": False,
                },
            },
        )

    monkeypatch.setattr(module, "_command_json", successful_backend_command)
    monkeypatch.setattr(module, "_deploy_mcp_from_ci_scope", failed_mcp_preflight)

    result = module.reconcile()

    assert result["status"] == "MCP_UPDATE_FAILED_BACKEND_ROLLBACK_ATTEMPTED"
    assert result["revision"] == scope["revision"]
    assert result["mutationEvidenceStatus"] == "PERFORMED"
    assert result["mutationPerformed"] is True
    assert result["backendDeploy"]["mutationPerformed"] is True
    assert result["mcpUpdate"]["mutationEvidenceStatus"] == "UNKNOWN"
    assert "mutationPerformed" not in result["mcpUpdate"]
    assert result["rollback"]["attempted"] is True
    assert len(command_calls) == 2


def test_backend_deploy_subprocess_receives_installer_selected_env_file(
    monkeypatch, tmp_path
) -> None:
    module, scope, _previous_backend, _current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path
    )
    captured: dict[str, Any] = {}

    def capturing_command(argv, *, timeout=None, stage=None, environment=None):
        captured["argv"] = list(argv)
        captured["stage"] = stage
        captured["environment"] = dict(environment) if environment else {}
        return {"receipt": {"ok": True}, "outputSha256": "a" * 64}

    monkeypatch.setattr(module, "_command_json", capturing_command)
    monkeypatch.setattr(
        module,
        "_deploy_mcp_from_ci_scope",
        lambda *_args, **_kwargs: {"status": "DEPLOYED", "revision": scope["revision"]},
    )
    monkeypatch.setattr(
        module, "_runtime_readback", lambda *_args, **_kwargs: {"backend": {}, "mcp": {}, "broker": {}, "patchmon": {"status": "VERIFIED"}}
    )

    result = module.reconcile()

    assert result["status"] == "COORDINATED_RELEASE_DEPLOYED"
    env_file = result["backendDeploy"]["backendEnvFile"]
    assert env_file == str(tmp_path / "backend.env")
    assert env_file in module.SANCTIONED_BACKEND_ENV_PATHS
    assert captured["environment"]["SOVEREIGN_BACKEND_ENV_FILE"] == env_file
    assert captured["stage"] == "backend_deploy"
    assert str(module.BACKEND_DEPLOY) in captured["argv"][0]


def test_backend_rollback_subprocess_reuses_installer_selected_env_file(
    monkeypatch, tmp_path
) -> None:
    module, scope, _previous_backend, _current_backend = _scoped_reconcile_fixture(
        monkeypatch, tmp_path
    )
    captured_envs: list[str] = []

    def capturing_command(argv, *, timeout=None, stage=None, environment=None):
        captured_envs.append(
            environment.get("SOVEREIGN_BACKEND_ENV_FILE", "") if environment else ""
        )
        return {"receipt": {"ok": True}, "outputSha256": "b" * 64}

    monkeypatch.setattr(module, "_command_json", capturing_command)

    def failed_mcp_preflight(*_args, **_kwargs):
        raise module.ReconcileError(
            "mcp_deploy",
            "exit=1;outputSha256=" + "9" * 64,
            safe_evidence={
                "outputSha256": "9" * 64,
                "installerDiagnostic": {
                    "stage": "preflight",
                    "rollbackAttempted": False,
                },
            },
        )

    monkeypatch.setattr(module, "_deploy_mcp_from_ci_scope", failed_mcp_preflight)

    result = module.reconcile()

    assert result["status"] == "MCP_UPDATE_FAILED_BACKEND_ROLLBACK_ATTEMPTED"
    # Two subprocesses: backend deploy then backend rollback; both share the
    # installer-selected canonical env pointer.
    assert len(captured_envs) == 2
    assert captured_envs[0] == captured_envs[1]
    assert captured_envs[0] == str(tmp_path / "backend.env")
    assert captured_envs[0] in module.SANCTIONED_BACKEND_ENV_PATHS


def test_backend_env_resolver_fails_closed_when_managed_env_missing(monkeypatch, tmp_path) -> None:
    module = _load()
    monkeypatch.setattr(module, "MANAGED_RUNTIME_ENV", tmp_path / "absent.env")
    monkeypatch.setattr(
        module, "SANCTIONED_BACKEND_ENV_PATHS", frozenset({str(tmp_path / "backend.env")})
    )
    with pytest.raises(module.ReconcileError) as caught:
        module._resolve_backend_env_file()
    assert caught.value.stage == "backend_env_binding"


def test_backend_env_resolver_fails_closed_when_pointer_unsanctioned(monkeypatch, tmp_path) -> None:
    module = _load()
    unsanctioned = tmp_path / "evil.env"
    unsanctioned.write_text("KEY=not-a-secret-fixture\n", "utf-8")
    managed_env_file = tmp_path / "runtime.env"
    managed_env_file.write_text(f"SOVEREIGN_BACKEND_ENV_FILE={unsanctioned}\n", "utf-8")
    monkeypatch.setattr(module, "MANAGED_RUNTIME_ENV", managed_env_file)
    monkeypatch.setattr(
        module, "SANCTIONED_BACKEND_ENV_PATHS", frozenset({str(tmp_path / "sanctioned.env")})
    )
    with pytest.raises(module.ReconcileError) as caught:
        module._resolve_backend_env_file()
    assert caught.value.stage == "backend_env_binding"


def test_backend_env_resolver_fails_closed_when_pointer_is_symlink(monkeypatch, tmp_path) -> None:
    module = _load()
    real_env = tmp_path / "backend.env"
    real_env.write_text("KEY=not-a-secret-fixture\n", "utf-8")
    symlinked_env = tmp_path / "linked.env"
    symlinked_env.symlink_to(real_env)
    managed_env_file = tmp_path / "runtime.env"
    managed_env_file.write_text(f"SOVEREIGN_BACKEND_ENV_FILE={symlinked_env}\n", "utf-8")
    monkeypatch.setattr(module, "MANAGED_RUNTIME_ENV", managed_env_file)
    monkeypatch.setattr(
        module, "SANCTIONED_BACKEND_ENV_PATHS", frozenset({str(symlinked_env)})
    )
    with pytest.raises(module.ReconcileError) as caught:
        module._resolve_backend_env_file()
    assert caught.value.stage == "backend_env_binding"


def test_backend_env_resolver_fails_closed_when_sanctioned_file_missing(monkeypatch, tmp_path) -> None:
    module = _load()
    sanctioned_but_absent = tmp_path / "backend.env"
    managed_env_file = tmp_path / "runtime.env"
    managed_env_file.write_text(f"SOVEREIGN_BACKEND_ENV_FILE={sanctioned_but_absent}\n", "utf-8")
    monkeypatch.setattr(module, "MANAGED_RUNTIME_ENV", managed_env_file)
    monkeypatch.setattr(
        module, "SANCTIONED_BACKEND_ENV_PATHS", frozenset({str(sanctioned_but_absent)})
    )
    with pytest.raises(module.ReconcileError) as caught:
        module._resolve_backend_env_file()
    assert caught.value.stage == "backend_env_binding"


def test_command_failure_returns_only_bounded_diagnostics_and_output_hash(monkeypatch) -> None:
    module = _load()
    raw_secret = "super-secret-runtime-value"
    completed = subprocess.CompletedProcess(
        ["deploy"],
        1,
        "SOVEREIGN_DEPLOY_DIAGNOSTIC:admin_canary:ContractFailure\n",
        raw_secret,
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: completed)

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["deploy"], timeout=10, stage="backend_deploy")

    error = caught.value
    assert error.safe_evidence["diagnostics"] == [
        {"stage": "admin_canary", "failureFamily": "ContractFailure"}
    ]
    assert len(error.safe_evidence["outputSha256"]) == 64
    assert raw_secret not in json.dumps(error.safe_evidence)
    assert raw_secret not in error.detail


def test_mcp_installer_failure_returns_stage_without_reason(monkeypatch) -> None:
    module = _load()
    raw_secret = "private-installer-reason"
    completed = subprocess.CompletedProcess(
        ["install"],
        1,
        "",
        (
            "install blocked: stage=replace_mcp_container exit=1 "
            f"reason={raw_secret} rollback_attempted=1\n"
        ),
    )
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: completed)

    with pytest.raises(module.ReconcileError) as caught:
        module._command_json(["install"], timeout=10, stage="mcp_deploy")

    evidence = caught.value.safe_evidence
    assert evidence["installerDiagnostic"] == {
        "stage": "replace_mcp_container",
        "rollbackAttempted": True,
    }
    assert raw_secret not in json.dumps(evidence)
    assert raw_secret not in caught.value.detail


def test_mcp_deploy_runs_ci_scoped_non_executable_installer_through_fixed_bash(
    monkeypatch, tmp_path
) -> None:
    module = _load()
    revision = "f" * 40
    digest = "sha256:" + "1" * 64
    checkout = tmp_path / "checkout"
    installer = checkout / "tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh"
    installer.parent.mkdir(parents=True)
    receipt = {
        "ok": True,
        "mcp_revision": revision,
        "mcp_image": f"{module.MCP_REPOSITORY}@{digest}",
        "host_command_worker_active": True,
        "broker": "active",
        "broker_rpc_ready": True,
        "broker_socket_host_visible": True,
        "broker_socket_container_visible": True,
        "mcp_protocol_ready": True,
        "self_update_available": False,
        "pr_lifecycle_available": False,
        "workflow_dispatch_available": False,
    }
    installer.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        f"[ \"$SOVEREIGN_MCP_EXPECTED_REVISION\" = \"{revision}\" ]\n"
        f"[ \"$SOVEREIGN_MCP_EXPECTED_DIGEST\" = \"{digest}\" ]\n"
        f"printf '%s\\n' '{json.dumps(receipt, separators=(',', ':'))}'\n",
        "utf-8",
    )
    installer.chmod(0o644)
    monkeypatch.setenv("PATH", "")

    result = module._deploy_mcp_from_ci_scope(
        revision,
        {"digest": digest},
        {
            "revision": revision,
            "path": str(checkout),
            "installer": str(installer),
        },
    )

    assert installer.stat().st_mode & 0o111 == 0
    assert result["status"] == "DEPLOYED"
    assert result["revision"] == revision
    assert result["digest"] == digest


def test_global_failure_fallback_never_claims_no_mutation(monkeypatch, tmp_path) -> None:
    module = _load()
    revision = "7" * 40
    monkeypatch.setattr(module, "STATE_DIR", tmp_path)
    monkeypatch.setattr(module, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(module, "LOCK_FILE", tmp_path / "reconcile.lock")
    monkeypatch.setattr(module, "GITHUB_TOKEN_FILE", tmp_path / "ephemeral-token")
    module.EXPECTED_REVISION = revision
    module.EXPECTED_RELEASE_GATE_RUN_ID = "92"
    module.EXPECTED_BACKEND_DIGEST = "sha256:" + "8" * 64
    module.EXPECTED_MCP_DIGEST = "sha256:" + "9" * 64
    module.EXPECTED_MANIFEST_EVIDENCE_SHA256 = "a" * 64
    monkeypatch.setattr(
        module,
        "reconcile",
        lambda: (_ for _ in ()).throw(module.ReconcileError("host_command", "timeout")),
    )

    exit_code = module.main()
    result = json.loads((tmp_path / "status.json").read_text("utf-8"))

    assert exit_code == 1
    assert result["revision"] == revision
    assert result["mutationEvidenceStatus"] == "UNKNOWN"
    assert "mutationPerformed" not in result
    assert result["retryable"] is False


@pytest.mark.parametrize(
    ("receipt", "expected_exit"),
    [
        ({"ok": False, "status": "BACKEND_DEPLOY_FAILED"}, 1),
        ({"ok": False, "status": "RUNTIME_READBACK_FAILED"}, 1),
        ({"ok": False, "status": "WAITING_FOR_RELEASE_GATE"}, 0),
        ({"ok": True, "status": "COORDINATED_RELEASE_DEPLOYED"}, 0),
    ],
)
def test_main_propagates_terminal_reconcile_failures(
    monkeypatch, tmp_path, receipt, expected_exit
) -> None:
    module = _load()
    monkeypatch.setattr(module, "STATE_DIR", tmp_path)
    monkeypatch.setattr(module, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(module, "LOCK_FILE", tmp_path / "reconcile.lock")
    monkeypatch.setattr(module, "GITHUB_TOKEN_FILE", tmp_path / "ephemeral-token")
    module.EXPECTED_REVISION = "b" * 40
    module.EXPECTED_RELEASE_GATE_RUN_ID = "93"
    module.EXPECTED_BACKEND_DIGEST = "sha256:" + "c" * 64
    module.EXPECTED_MCP_DIGEST = "sha256:" + "d" * 64
    module.EXPECTED_MANIFEST_EVIDENCE_SHA256 = "e" * 64
    monkeypatch.setattr(module, "reconcile", lambda: dict(receipt))

    assert module.main() == expected_exit


def test_self_runtime_readback_accepts_only_the_expected_in_progress_release_run_contract() -> None:
    source = SCRIPT.read_text("utf-8")
    assert "expected_runtime_readback_run_id: int | None = None" in source
    assert 'evidence["runId"] == expected_runtime_readback_run_id' in source
    assert '"status": "RELEASE_GATE_SELF_RUNTIME_READBACK_ACTIVE"' in source
    assert "expected_runtime_readback_run_id=scope[\"releaseGateRunId\"]" in source
    assert 'return {"ready": False, "status": "WAITING_FOR_RELEASE_GATE", **evidence}' in source


def _git(*arguments: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_operator_source_refresh_uses_a_real_isolated_git_worktree_and_blocks_stale_main(
    monkeypatch, tmp_path
) -> None:
    upstream = tmp_path / "upstream"
    source = tmp_path / "source"
    checkouts = tmp_path / "checkouts"
    upstream.mkdir()
    _git("init", "-b", "main", cwd=upstream)
    _git("config", "user.email", "contract@example.invalid", cwd=upstream)
    _git("config", "user.name", "Source Contract", cwd=upstream)
    installer = upstream / "tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh"
    installer.parent.mkdir(parents=True)
    installer.write_text("#!/bin/sh\nexit 0\n", "utf-8")
    installer.chmod(0o700)
    (upstream / "revision.txt").write_text("first\n", "utf-8")
    _git("add", ".", cwd=upstream)
    _git("commit", "-m", "first", cwd=upstream)
    first_revision = _git("rev-parse", "HEAD", cwd=upstream)
    subprocess.run(["git", "clone", str(upstream), str(source)], check=True, capture_output=True, text=True)

    # This simulates the live installer-modified source root. The actual refresh
    # must leave this tree untouched and build its CI-scoped worktree separately.
    (source / "revision.txt").write_text("local-installer-mutation\n", "utf-8")
    assert _git("status", "--porcelain", cwd=source)

    module = _load()
    monkeypatch.setattr(module, "OPERATOR_SOURCE", source)
    monkeypatch.setattr(module, "OPERATOR_SOURCE_CHECKOUTS", checkouts)
    monkeypatch.setattr(module, "_github_token", lambda: "external-adapter-token-for-local-git-contract")
    scope = {"revision": first_revision}

    refreshed = module._refresh_operator_source(scope)
    checkout = checkouts / first_revision

    assert refreshed["revision"] == first_revision
    assert Path(refreshed["path"]) == checkout
    assert Path(refreshed["installer"]) == checkout / "tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh"
    assert _git("rev-parse", "HEAD", cwd=checkout) == first_revision
    assert _git("status", "--porcelain", cwd=checkout) == ""
    assert _git("status", "--porcelain", cwd=source)

    (upstream / "revision.txt").write_text("second\n", "utf-8")
    _git("add", "revision.txt", cwd=upstream)
    _git("commit", "-m", "second", cwd=upstream)

    with pytest.raises(module.ReconcileError, match="origin/main differs from CI scope revision"):
        module._refresh_operator_source(scope)


def test_candidate_failure_is_not_a_global_series_rollback_contract() -> None:
    source = (ROOT / "github_admin.py").read_text("utf-8")
    assert "PR_SERIES_COMPLETED_WITH_SKIPS" in source
    assert '"candidate_failures_are_quarantined": True' in source
    assert '"already_merged_prs_are_never_rolled_back": True' in source
    assert "PR_SERIES_HALTED_SYSTEMIC" in source
    assert "MAX_PR_SERIES = 500" in source


def test_workflows_and_installer_bind_coordinated_release_contract() -> None:
    coordinated = (REPOSITORY_ROOT / ".github/workflows/sovereign-coordinated-release.yml").read_text("utf-8")
    mcp_workflow = (REPOSITORY_ROOT / ".github/workflows/sovereign-chatgpt-mcp.yml").read_text("utf-8")
    installer_path = ROOT / "deploy/install-on-vps.sh"
    installer = installer_path.read_text("utf-8")
    service = (ROOT / "deploy/sovereign-release-reconciler.service").read_text("utf-8")
    timer = (ROOT / "deploy/sovereign-release-reconciler.timer").read_text("utf-8")

    assert "sovereign-backend-image.yml" in coordinated
    assert "sovereign-chatgpt-mcp.yml" in coordinated
    assert "head_sha: expected" in coordinated
    assert "EXACT_REVISION_IMAGE_WORKFLOWS_VERIFIED" in coordinated
    assert "org.opencontainers.image.revision" in coordinated
    push_prefix = mcp_workflow.split("workflow_dispatch:", 1)[0]
    assert "paths:" not in push_prefix
    assert 'remove_value "$ENV_FILE" GITHUB_TOKEN' in installer
    assert 'remove_value "$MANAGED_ENV" GITHUB_TOKEN' in installer
    assert "printf 'GITHUB_TOKEN=%s\\n' \"$EFFECTIVE_GITHUB_TOKEN\"" not in installer
    assert 'SOVEREIGN_MCP_EXPECTED_DIGEST' in installer
    assert 'MCP image digest differs from CI-bound expected digest' in installer
    assert 'SOVEREIGN_MCP_ENABLE_MAIN_PUSH \\' in installer
    assert 'SOVEREIGN_MCP_ENABLE_PR_MERGE \\' in installer
    assert 'SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL \\' in installer
    assert 'set_value "$MANAGED_ENV" "$TOKEN_DEPENDENT_CAPABILITY" "0"' in installer
    assert '"self_update_available":false' in installer
    assert '"pr_lifecycle_available":false' in installer
    assert '"workflow_dispatch_available":false' in installer
    assert 'install_ci_runtime_readback_authorization' in installer
    assert "systemctl enable --now sovereign-release-reconciler.timer" in installer
    assert "ExecStart=/opt/sovereign-chatgpt-tools/bin/reconcile-main-release" in service
    assert "OnUnitActiveSec=2min" in timer
    assert installer_path.stat().st_mode & 0o111 == 0o111
    reconciler = SCRIPT.read_text("utf-8")
    assert "_schedule_self_update" not in reconciler
    assert "def _deploy_mcp_from_ci_scope" in reconciler
    assert '["/bin/bash", str(installer)]' in reconciler
    assert '"SOVEREIGN_MCP_EXPECTED_DIGEST": mcp["digest"]' in reconciler
    assert "def _refresh_operator_source" in reconciler
    assert '"git", "-C", str(OPERATOR_SOURCE), "fetch", "--no-tags", "origin", "main"' in reconciler
    assert '"git", "-C", str(OPERATOR_SOURCE), "worktree", "add", "--detach", str(checkout), revision' in reconciler
    assert "OPERATOR_SOURCE_CHECKOUTS" in reconciler
    assert "origin/main differs from CI scope revision" in reconciler
    assert "scoped operator worktree is not clean" in reconciler
    assert "scoped operator worktree revision differs from CI scope" in reconciler
    assert "operator source worktree is not clean" not in reconciler
    assert "installer source revision is not CI-scoped" in reconciler
    assert "installer path is not CI-scoped" in reconciler
    assert "installer receipt violates CI scope or capability truth" in reconciler
    assert 'receipt.get("host_command_worker_active") is not True' in reconciler
    assert 'receipt.get("broker") != "active"' in reconciler
    assert 'receipt.get("broker_rpc_ready") is not True' in reconciler
    assert 'receipt.get("broker_socket_host_visible") is not True' in reconciler
    assert 'receipt.get("broker_socket_container_visible") is not True' in reconciler
    assert 'receipt.get("mcp_protocol_ready") is not True' in reconciler
