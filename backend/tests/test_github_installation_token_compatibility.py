"""Input and redaction regressions, not evidence of a live Draft PR.

All credentials here are generated, nonfunctional fixtures. The credential
handoff test executes the real askpass process, without contacting GitHub.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime.contracts import (  # noqa: E402
    SovereignAgentEvent,
    normalize_agent_event,
    sanitize_agent_text,
)
from agent_runtime.git_workspace import (  # noqa: E402
    git_credential_environment,
    normalize_ephemeral_github_token,
)


def installation_token() -> str:
    return "ghs_" + "12345_" + ".".join((
        "header-opaque" * 5,
        "payload_opaque" * 36,
        "signature-opaque" * 6,
    ))


def test_accepts_opaque_variable_length_installation_token_without_decoding() -> None:
    token = installation_token()
    assert len(token) > 520
    assert normalize_ephemeral_github_token(token) == token
    assert normalize_ephemeral_github_token(f" {token} ") == token


@pytest.mark.parametrize("prefix", ["ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"])
def test_preserves_legacy_formats(prefix: str) -> None:
    token = prefix + "a" * 36
    assert normalize_ephemeral_github_token(token) == token


@pytest.mark.parametrize("value", [None, 123, {}, [], "", "invalid"])
def test_rejects_missing_or_noncredential_inputs(value: object) -> None:
    assert normalize_ephemeral_github_token(value) is None


@pytest.mark.parametrize("suffix", ["\r\nInjected: value", "\x00", "/", "\"", "é", " middle space"])
def test_rejects_unsafe_installation_token_characters(suffix: str) -> None:
    assert normalize_ephemeral_github_token(installation_token() + suffix) is None


def test_installation_token_is_bounded_without_truncation() -> None:
    assert normalize_ephemeral_github_token("ghs_" + "a." * 2048) is not None
    assert normalize_ephemeral_github_token("ghs_" + "a." * 2048 + "x") is None


@pytest.mark.parametrize("prefix", ["", "credential: ", "Authorization: Bearer "])
def test_entire_opaque_credential_is_redacted(prefix: str) -> None:
    token = installation_token()
    output = sanitize_agent_text(prefix + token)
    assert "[redacted]" in output
    assert token not in output
    for fragment in ("12345", "header-opaque", "payload_opaque", "signature-opaque"):
        assert fragment not in output


def test_raw_installation_token_redaction_is_idempotent() -> None:
    output = sanitize_agent_text(installation_token())
    assert output == "ghs_[redacted]"
    assert sanitize_agent_text(output) == output


def test_rejected_oversized_credential_is_still_fully_masked_before_text_cap() -> None:
    token = "ghs_" + "opaque.part-" * 600
    assert normalize_ephemeral_github_token(token) is None
    assert sanitize_agent_text(token, 64) == "ghs_[redacted]"


def test_runtime_event_cannot_retain_any_installation_token_segment() -> None:
    token = installation_token()
    event = normalize_agent_event(SovereignAgentEvent(
        stage="github_preflight",
        level="error",
        message=f"Rejected {token}",
        at=1,
    ))
    payload = json.dumps(asdict(event))
    assert token not in payload
    assert "payload_opaque" not in payload
    assert "signature-opaque" not in payload
    assert "[redacted]" in payload


def test_real_askpass_handoff_never_writes_credential_to_disk(tmp_path: Path) -> None:
    token = installation_token()
    with git_credential_environment(token, tmp_path) as env:
        assert env is not None
        script = Path(env["GIT_ASKPASS"])
        assert script.is_file()
        assert script.stat().st_mode & 0o077 == 0
        assert token not in script.read_text(encoding="utf-8")
        password = subprocess.run(
            [str(script), "Password for GitHub"],
            env=env, capture_output=True, text=True, shell=False,
            timeout=5, check=True,
        )
        assert password.stdout == token + "\n"
        assert password.stderr == ""
        for file in tmp_path.iterdir():
            if file.is_file():
                assert token.encode() not in file.read_bytes()
    assert not script.exists()
    assert token not in os.environ.values()


@pytest.mark.parametrize("name", ["git_workspace.py", "contracts.py"])
def test_production_mirror_bytes_are_identical(name: str) -> None:
    assert (ROOT / "backend" / "agent_runtime" / name).read_bytes() == (
        ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / name
    ).read_bytes()
