from __future__ import annotations

import ast
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))

from freellm_provider_credentials import (
    FREELLM_PROVIDER_SPECS,
    normalize_freellm_provider_id,
    provider_id_from_target_id,
    provider_keyless_marker_path,
    provider_secret_path,
    provider_target_id,
)


def test_provider_allowlist_has_keyed_and_keyless_contracts(tmp_path: Path) -> None:
    assert FREELLM_PROVIDER_SPECS["groq"]["keyless"] is False
    assert FREELLM_PROVIDER_SPECS["pollinations"]["keyless"] is False
    assert FREELLM_PROVIDER_SPECS["ovh"]["keyless"] is True
    assert FREELLM_PROVIDER_SPECS["kilo"]["keyless"] is True
    assert FREELLM_PROVIDER_SPECS["aihorde"]["keyless"] is True
    assert provider_secret_path(tmp_path, "groq") == tmp_path / "freellm-provider-keys" / "groq.key"
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


def test_provider_target_ids_round_trip_and_reject_unknown_values() -> None:
    target_id = provider_target_id("openrouter")
    assert target_id == "freellm_provider_openrouter_key"
    assert provider_id_from_target_id(target_id) == "openrouter"
    with pytest.raises(ValueError, match="provider_id_invalid"):
        normalize_freellm_provider_id("unknown-provider")
    with pytest.raises(ValueError, match="target_id_invalid"):
        provider_id_from_target_id("freellm_provider_unknown_key")


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
    assert "request.get_data" in owner
    assert "protected_buffer[index] = 0" in owner
    assert "FreeLLM Provider-Zugänge" in page
    assert "type=\"password\"" in page


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
