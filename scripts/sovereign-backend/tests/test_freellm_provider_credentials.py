from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))

from freellm_provider_credentials import (
    FREELLM_PROVIDER_SPECS,
    detect_freellm_provider_id_from_key,
    normalize_freellm_provider_id,
    provider_id_from_target_id,
    provider_keyless_marker_path,
    provider_secret_path,
    provider_secret_paths,
    provider_secret_pool_path,
    provider_target_id,
)
import free_revolver_provider_runtime as provider_runtime


def test_provider_allowlist_has_keyed_and_keyless_contracts(tmp_path: Path) -> None:
    assert FREELLM_PROVIDER_SPECS["groq"]["keyless"] is False
    assert FREELLM_PROVIDER_SPECS["pollinations"]["keyless"] is False
    assert FREELLM_PROVIDER_SPECS["ovh"]["keyless"] is True
    assert FREELLM_PROVIDER_SPECS["kilo"]["keyless"] is True
    assert FREELLM_PROVIDER_SPECS["aihorde"]["keyless"] is False
    assert provider_secret_path(tmp_path, "groq") == tmp_path / "freellm-provider-keys" / "groq.key"
    fingerprint = "a" * 64
    second_fingerprint = "b" * 64
    pooled = provider_secret_pool_path(tmp_path, "groq", fingerprint)
    pooled_second = provider_secret_pool_path(tmp_path, "groq", second_fingerprint)
    assert pooled == tmp_path / "freellm-provider-keys" / f"groq.{fingerprint}.key"
    assert pooled_second != pooled
    assert provider_secret_pool_path(tmp_path, "groq", fingerprint) == pooled
    pooled.parent.mkdir(parents=True)
    pooled.write_text("gsk_" + "x" * 24, encoding="utf-8")
    pooled_second.write_text("gsk_" + "y" * 24, encoding="utf-8")
    discovered_paths = provider_secret_paths(tmp_path, "groq")
    assert pooled in discovered_paths
    assert pooled_second in discovered_paths
    assert len([path for path in discovered_paths if path.is_file()]) == 2
    assert provider_secret_path(tmp_path, "pollinations") == (
        tmp_path / "freellm-provider-keys" / "pollinations.key"
    )
    assert provider_keyless_marker_path(tmp_path, "kilo") == (
        tmp_path / "freellm-provider-keys" / "kilo.keyless"
    )
    assert provider_keyless_marker_path(tmp_path, "ovh") == (
        tmp_path / "freellm-provider-keys" / "ovh.keyless"
    )
    with pytest.raises(ValueError, match="provider_not_keyless"):
        provider_keyless_marker_path(tmp_path, "pollinations")
    with pytest.raises(ValueError, match="provider_not_keyless"):
        provider_keyless_marker_path(tmp_path, "aihorde")


def test_provider_target_ids_round_trip_and_reject_unknown_values() -> None:
    target_id = provider_target_id("openrouter")
    assert target_id == "freellm_provider_openrouter_key"
    assert provider_id_from_target_id(target_id) == "openrouter"
    with pytest.raises(ValueError, match="provider_id_invalid"):
        normalize_freellm_provider_id("unknown-provider")
    with pytest.raises(ValueError, match="target_id_invalid"):
        provider_id_from_target_id("freellm_provider_unknown_key")


def test_provider_key_detection_is_strong_and_fail_closed() -> None:
    assert detect_freellm_provider_id_from_key(bytearray(b"AQ." + b"x" * 24)) == "google"
    assert detect_freellm_provider_id_from_key(bytearray(b"AIza-" + b"x" * 24)) == "google"
    assert detect_freellm_provider_id_from_key(bytearray(b"gsk_" + b"x" * 24)) == "groq"
    assert detect_freellm_provider_id_from_key(bytearray(b"sk-or-v1-" + b"x" * 24)) == "openrouter"
    assert detect_freellm_provider_id_from_key(bytearray(b"github_pat_" + b"x" * 24)) == "github"
    assert detect_freellm_provider_id_from_key(bytearray(b"nvapi-" + b"x" * 24)) == "nvidia"
    assert detect_freellm_provider_id_from_key(bytearray(b"hf_" + b"x" * 24)) == "huggingface"
    with pytest.raises(ValueError, match="provider_key_unrecognized"):
        detect_freellm_provider_id_from_key(bytearray(b"opaque-" + b"x" * 24))


def test_recognized_provider_key_is_persisted_and_read_back_from_the_owner_pool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A recognized key is durable without ever placing its raw value in PostgreSQL."""
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    monkeypatch.setattr(provider_runtime.os, "geteuid", lambda: 0)
    monkeypatch.setattr(provider_runtime.os, "fchown", lambda *_args: None)
    monkeypatch.setattr(provider_runtime.os, "chown", lambda *_args: None)

    raw_key = b"gsk_" + b"x" * 24
    protected = bytearray(b"  " + raw_key + b"\n")
    expected_fingerprint = hashlib.sha256(raw_key).hexdigest()
    try:
        fingerprint = provider_runtime._write_freellm_provider_key("groq", protected)
        saved_path = provider_secret_pool_path(tmp_path, "groq", fingerprint)
        state = provider_runtime._freellm_provider_credential_state("groq")

        assert fingerprint == expected_fingerprint
        assert saved_path.read_bytes() == raw_key
        assert state == {
            "configured": True,
            "mode": "credential-pool",
            "keyCount": 1,
            "fingerprintSha256": expected_fingerprint,
            "permissionsValid": True,
        }
        assert provider_runtime._write_freellm_provider_key("groq", protected) == fingerprint
        assert provider_runtime._freellm_provider_credential_state("groq")["keyCount"] == 1
    finally:
        for index in range(len(protected)):
            protected[index] = 0


def test_owner_input_and_runtime_expose_only_safe_provider_metadata() -> None:
    owner = (BACKEND / "owner_input_runtime.py").read_text("utf-8")
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    page = (BACKEND / "freellm_provider_admin_page.py").read_text("utf-8")
    ast.parse(owner)
    ast.parse(runtime)
    ast.parse(page)

    assert "provider_secret_path(_root(), provider_id)" in owner
    assert '"databaseCredentialStorage": False' in runtime
    assert '"rawCredentialsReturned": False' in runtime
    assert '"rawCredentialReturned": False' in runtime
    assert '"/freellm-provider-keys"' in runtime
    assert '"/api/admin/llm/freellm/provider-credentials/auto"' in runtime
    assert "detect_freellm_provider_id_from_key(protected)" in runtime
    assert "protected[index] = 0" in runtime
    assert "request.get_data" in owner
    assert "protected_buffer[index] = 0" in owner
    assert "FreeLLM Provider-Zugänge" in page
    assert "type=\"password\"" in page
    assert "/api/admin/llm/freellm/provider-credentials/auto" in page
    assert "X-FreeLLM-Provider-Id" in page
    assert "providerSelectionRequired" in page
    assert "p.keyCount" in page
    assert "def _prepare_freellm_secret_directory(" in runtime
    assert 'getattr(os, "O_NOFOLLOW", 0)' in runtime
    assert "os.fchmod(descriptor, 0o700)" in runtime


def test_react_admin_preserves_unknown_key_fallback_until_provider_selection() -> None:
    api_client = (
        REPO / "src" / "features" / "admin" / "api" / "adminApiClient.ts"
    ).read_text("utf-8")
    control_center = (
        REPO / "src" / "features" / "admin" / "components" / "FreeRevolverControlCenter.tsx"
    ).read_text("utf-8")
    hook = (
        REPO / "src" / "features" / "admin" / "hooks" / "useAdminApi.ts"
    ).read_text("utf-8")

    assert "FreellmProviderSelectionRequiredError" in api_client
    assert "'X-FreeLLM-Provider-Id': providerId" in api_client
    assert "body.providerSelectionRequired === true" in api_client
    assert "body.providers.length > 0" in api_client
    assert "setProviderChoices(error.providers)" in control_center
    assert "setApiKey('');" in control_center
    assert control_center.index("setApiKey('');") > control_center.index(".then(result =>")
    assert "api.autoConfigureKey(protectedValue, explicitProviderId)" in control_center
    assert "providerChoices.length > 0" in control_center
    assert "autoConfigureKey: (apiKey: string, providerId?: string)" in hook


def test_evidence_maintainer_is_single_worker_and_selects_only_ready_managed_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Cursor:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def execute(self, sql: str, _params) -> None:
            self.statements.append(sql)

        def fetchone(self):
            return {"acquired": True}

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()
            self.closed = False

        def cursor(self):
            return self.cursor_instance

        def close(self) -> None:
            self.closed = True

    connection = Connection()
    maintainer = provider_runtime._FreeLlmEvidenceMaintainer(lambda: connection)
    monkeypatch.setenv("SOVEREIGN_FREELLM_EVIDENCE_MAINTAINER_ENABLED", "1")
    monkeypatch.setattr(
        maintainer,
        "_request_json",
        lambda *_args, **_kwargs: (
            200,
            {
                "ok": True,
                "providers": [
                    {
                        "sourceId": "c79ff468-ee08-5686-97df-756fa58b74f0",
                        "sourceType": "freellmpool-private",
                        "enabled": True,
                        "managedKeyAvailable": True,
                    },
                    {
                        "sourceId": "1a866402-68c4-4f40-8d09-55ed8deabf68",
                        "sourceType": "freellmapi-direct",
                        "enabled": True,
                        "managedKeyAvailable": True,
                    },
                    {
                        "sourceId": "00000000-0000-0000-0000-000000000001",
                        "sourceType": "external-free-provider",
                        "enabled": True,
                        "managedKeyAvailable": False,
                    },
                ],
            },
        ),
    )
    selected: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        maintainer,
        "_run_provider",
        lambda source_id, *, force_discovery: selected.append((source_id, force_discovery)),
    )

    assert maintainer.run_once(force_discovery=True) is True
    assert selected == [
        ("1a866402-68c4-4f40-8d09-55ed8deabf68", True),
        ("c79ff468-ee08-5686-97df-756fa58b74f0", True),
    ]
    assert any("pg_try_advisory_lock" in sql for sql in connection.cursor_instance.statements)
    assert any("pg_advisory_unlock" in sql for sql in connection.cursor_instance.statements)
    assert connection.closed is True


def test_evidence_maintainer_advances_bounded_batches_until_candidate_signature_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maintainer = provider_runtime._FreeLlmEvidenceMaintainer(lambda: None)
    monkeypatch.setenv("SOVEREIGN_FREELLM_EVIDENCE_MAINTAINER_MAX_MODELS", "2")
    monkeypatch.setenv("SOVEREIGN_FREELLM_EVIDENCE_MAINTAINER_MAX_ROUNDS", "6")
    calls: list[tuple[str, dict | None]] = []
    reconcile_results = iter([
        (409, {"deferred": [{"modelId": "a"}, {"modelId": "b"}]}),
        (409, {"deferred": [{"modelId": "c"}, {"modelId": "d"}]}),
        (409, {"deferred": [{"modelId": "c"}, {"modelId": "d"}]}),
    ])

    def fake_request(path: str, *, method: str = "GET", payload=None, timeout_seconds: int = 120):
        calls.append((path, payload))
        if path.endswith("/discover"):
            return 200, {"ok": True}
        return next(reconcile_results)

    monkeypatch.setattr(maintainer, "_request_json", fake_request)
    maintainer._run_provider("1a866402-68c4-4f40-8d09-55ed8deabf68", force_discovery=True)

    assert calls[0][0].endswith("/discover")
    reconcile_calls = [item for item in calls if item[0].endswith("/reconcile")]
    assert len(reconcile_calls) == 3
    assert all(item[1] == {"maxModels": 2} for item in reconcile_calls)


def test_bootstrap_reads_only_bounded_private_files_and_drops_privileges() -> None:
    bootstrap = (
        REPO
        / "tools"
        / "sovereign-chatgpt-mcp"
        / "templates"
        / "sovereign-freellmapi"
        / "sovereign-freellm-bootstrap.mjs"
    ).read_text("utf-8")

    assert "info.isSymbolicLink()" in bootstrap
    assert "(info.mode & 0o077) !== 0" in bootstrap
    assert "info.size > 8192" in bootstrap
    assert "protectedValue.fill(0)" in bootstrap
    assert "process.getuid() !== RUNTIME_UID" in bootstrap
    assert "process.getgid() !== RUNTIME_GID" in bootstrap
    assert "process.setuid" not in bootstrap
    assert "process.setgid" not in bootstrap
    assert "setInterval" in bootstrap
    assert "15_000" in bootstrap
    assert "appliedFingerprints" in bootstrap
    assert "FREEAPI_CONFIG_PATH" in bootstrap
    assert "mode: 0o600" in bootstrap
    assert "flag: 'wx'" in bootstrap
    assert "cleanupInitialConfigWhenReady" in bootstrap
    assert "fs.rmSync(initialConfigPath" in bootstrap
    assert bootstrap.index("await import('/app/server/dist/index.js')") < bootstrap.index("const { getDb }")
    assert "rawCredentialsReturned: false" in bootstrap
    assert "console.log(value)" not in bootstrap
