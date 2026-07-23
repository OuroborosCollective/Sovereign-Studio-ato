from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from managed_compose import (
    FREELLMPOOL_CONTAINER,
    FREELLMPOOL_DATA_VOLUME,
    FREELLMPOOL_ENTRYPOINT_COMMAND,
    FREELLMPOOL_IMAGE,
    FREELLMPOOL_OWNER_KEY_PATH,
    FREELLMPOOL_REPO_DIGEST,
    FREELLMPOOL_RUNTIME_CONTENT_SHA256,
    FREELLMPOOL_RUNTIME_GID,
    FREELLMPOOL_RUNTIME_UID,
    ManagedComposeRuntime,
    STACKS,
)


def _missing_runner(argv, **kwargs):
    return subprocess.CompletedProcess(argv, 1, "", "not found")


def test_freellmpool_template_is_private_immutable_non_root_and_secret_file_bound() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "sovereign-freellmpool"
    )
    template = (root / "docker-compose.yml").read_text("utf-8")
    entrypoint = (root / "freellmpool-entrypoint.py").read_text("utf-8")

    assert FREELLMPOOL_IMAGE in template
    assert "b5b131dec34a32925c6280611df9e9c0ede1ba6b39efb0e103a76064044f32fa" in template
    assert FREELLMPOOL_RUNTIME_CONTENT_SHA256 in template
    assert 'user: "10001:10001"' in template
    assert "read_only: true" in template
    assert "privileged: false" in template
    assert "no-new-privileges:true" in template
    assert "cap_drop:" in template and "- ALL" in template
    assert "ports:" not in template
    assert "sovereign-private:" in template and "external: true" in template
    assert "freellmpool-data:/var/lib/freellmpool" in template
    assert "freellmpool_proxy_key.txt:/run/secrets/freellmpool_proxy_key:ro" in template
    assert "/var/run/docker.sock" not in template
    assert "FREELLMPOOL_PROXY_KEY:" not in template
    assert "KEY_PATH = Path(\"/run/secrets/freellmpool_proxy_key\")" in entrypoint
    assert "os.execvp(" in entrypoint
    assert '"python",\n            "-m",\n            "freellmpool.cli"' in entrypoint


def test_freellmpool_image_lock_matches_runtime_and_ci_verifies_without_rebuild() -> None:
    root = Path(__file__).resolve().parents[1]
    lock_path = (
        root
        / "templates"
        / "sovereign-freellmpool"
        / "freellmpool-image.lock.json"
    )
    lock = json.loads(lock_path.read_text("utf-8"))
    workflow = (
        root.parents[1]
        / ".github"
        / "workflows"
        / "sovereign-freellmpool-verify.yml"
    ).read_text("utf-8")

    assert lock["image"] == FREELLMPOOL_IMAGE
    assert lock["upstreamRevision"] == "f9e09e536682083297cfd6fec3ea5d3aac5262c8"
    assert lock["releaseVersion"] == "0.11.4"
    assert lock["verifiedContract"]["dockerSocketMounted"] is False
    assert lock["verifiedContract"]["hostPortsPublished"] is False
    assert lock["verifiedContract"]["minimumSuccessfulKeylessCanaries"] >= 1
    assert "Experimental upstream rebuild (manual maintenance only)" in workflow
    assert "if: ${{ false }}" in workflow
    assert "Resolve and verify the approved immutable image lock" in workflow
    assert 'docker pull "${repo_digest}"' in workflow
    assert "REPO_DIGEST" in workflow
    assert 'assert os.environ["REPO_DIGEST"] in values' in workflow
    assert '"baseImageClaimed": False' in workflow
    assert '"rebuildPerformed": False' in workflow


def test_freellmpool_render_contract_rejects_root_mutable_or_env_secret(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    original = STACKS["sovereign-freellmpool"]
    deploy_root = tmp_path / "deploy"
    key_path = tmp_path / "owner" / "freellmpool_proxy_key.txt"
    stack = type(original)(
        **{
            **original.__dict__,
            "deploy_root": str(deploy_root),
            "allowed_bind_roots": (str(deploy_root), str(key_path)),
        }
    )
    rendered = {
        "services": {
            "freellmpool": {
                "image": FREELLMPOOL_IMAGE,
                "user": "10001:10001",
                "command": FREELLMPOOL_ENTRYPOINT_COMMAND,
                "read_only": True,
                "privileged": False,
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
                "environment": {"HOME": "/var/lib/freellmpool"},
                "networks": ["sovereign-private"],
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(tmp_path / "staging" / "freellmpool-entrypoint.py"),
                        "target": "/opt/sovereign/freellmpool-entrypoint.py",
                    },
                    {
                        "type": "bind",
                        "source": str(key_path),
                        "target": "/run/secrets/freellmpool_proxy_key",
                    },
                ],
            }
        },
        "networks": {"sovereign-private": {}},
    }
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    runtime._validate_rendered(stack, rendered, staging_root=staging_root)

    rendered["services"]["freellmpool"]["user"] = "0:0"
    with pytest.raises(RuntimeError, match="Nicht-Root"):
        runtime._validate_rendered(stack, rendered, staging_root=staging_root)
    rendered["services"]["freellmpool"]["user"] = "10001:10001"
    rendered["services"]["freellmpool"]["read_only"] = False
    with pytest.raises(RuntimeError, match="read-only"):
        runtime._validate_rendered(stack, rendered, staging_root=staging_root)
    rendered["services"]["freellmpool"]["read_only"] = True
    rendered["services"]["freellmpool"]["environment"]["FREELLMPOOL_PROXY_KEY"] = "forbidden"
    with pytest.raises(RuntimeError, match="Umgebungswerten"):
        runtime._validate_rendered(stack, rendered, staging_root=staging_root)


def test_freellmpool_proxy_key_is_separate_private_and_not_returned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "owner" / "freellmpool_proxy_key.txt"
    deploy_root = tmp_path / "deploy"
    monkeypatch.setattr("managed_compose.FREELLMPOOL_OWNER_KEY_PATH", str(destination))
    monkeypatch.setattr("managed_compose.os.geteuid", lambda: 0)
    monkeypatch.setattr("managed_compose.os.chown", lambda path, uid, gid: None)
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    original = STACKS["sovereign-freellmpool"]
    stack = type(original)(**{**original.__dict__, "deploy_root": str(deploy_root)})

    result = runtime._ensure_stack_secret_env(stack)
    key = destination.read_text("utf-8").strip()

    assert result["created"] is True
    assert result["path"] == str(destination)
    assert result["mode"] == "0400"
    assert result["ownerUid"] == FREELLMPOOL_RUNTIME_UID
    assert result["ownerGid"] == FREELLMPOOL_RUNTIME_GID
    assert result["keyFingerprintSha256"] == hashlib.sha256(key.encode()).hexdigest()
    assert result["secretValuesReturned"] is False
    assert key not in str(result)
    assert destination.stat().st_mode & 0o777 == 0o400
    assert destination.parent.stat().st_mode & 0o777 == 0o700


def test_freellmpool_transport_requires_digest_security_mounts_private_network_and_no_ports() -> None:
    state = {
        "present": True,
        "running": True,
        "publishedPorts": {},
        "networks": ["sovereign-private"],
        "imageReference": FREELLMPOOL_IMAGE,
        "repoDigests": [FREELLMPOOL_REPO_DIGEST],
        "runtimeUser": "10001:10001",
        "readOnlyRootfs": True,
        "privileged": False,
        "capDrop": ["ALL"],
        "securityOpt": ["no-new-privileges:true"],
        "pidsLimit": 128,
        "mounts": [
            {
                "type": "volume",
                "name": FREELLMPOOL_DATA_VOLUME,
                "destination": "/var/lib/freellmpool",
                "rw": True,
            },
            {
                "type": "bind",
                "source": "/opt/sovereign-freellmpool/freellmpool-entrypoint.py",
                "destination": "/opt/sovereign/freellmpool-entrypoint.py",
                "rw": False,
            },
            {
                "type": "bind",
                "source": FREELLMPOOL_OWNER_KEY_PATH,
                "destination": "/run/secrets/freellmpool_proxy_key",
                "rw": False,
            },
        ],
    }

    assert ManagedComposeRuntime._freellmpool_transport_ready(state) is True
    state["publishedPorts"] = {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8080"}]}
    assert ManagedComposeRuntime._freellmpool_transport_ready(state) is False
    state["publishedPorts"] = {}
    state["runtimeUser"] = "0:0"
    assert ManagedComposeRuntime._freellmpool_transport_ready(state) is False
    state["runtimeUser"] = "10001:10001"
    state["readOnlyRootfs"] = False
    assert ManagedComposeRuntime._freellmpool_transport_ready(state) is False
    state["readOnlyRootfs"] = True
    state["capDrop"] = []
    assert ManagedComposeRuntime._freellmpool_transport_ready(state) is False


def test_freellmpool_runtime_canary_requires_two_real_confirmations_without_content(
    tmp_path: Path,
) -> None:
    receipt = (
        '{"ok":true,"modelCount":42,"verified":{'
        '"requestedModel":"pollinations/openai",'
        '"providerId":"pollinations",'
        '"providerModel":"openai",'
        '"responseModel":"openai",'
        '"confirmationCount":2},'
        '"attemptedCandidates":1,"rawResponsePersisted":false}'
    )

    def runner(argv, **kwargs):
        if argv[:4] == ["docker", "exec", "--user", "10001:10001"]:
            assert FREELLMPOOL_CONTAINER in argv
            assert "/run/secrets/freellmpool_proxy_key" in argv[-1]
            assert "for confirmation in (1, 2)" in argv[-1]
            return subprocess.CompletedProcess(argv, 0, receipt, "")
        return subprocess.CompletedProcess(argv, 1, "", "not found")

    runtime = ManagedComposeRuntime(runner=runner, template_root=str(tmp_path))
    result = runtime._freellmpool_runtime_canary()

    assert result["status"] == "FREELLMPOOL_DOUBLE_CANARY_VERIFIED"
    assert result["modelCount"] == 42
    assert result["providerId"] == "pollinations"
    assert result["canaryConfirmationCount"] == 2
    assert result["rawProviderResponsesReturned"] is False
    assert result["secretValuesReturned"] is False
