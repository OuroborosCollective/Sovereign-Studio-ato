from __future__ import annotations

import io
import json
import os
import sys
from urllib.error import HTTPError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.github_access import (  # noqa: E402
    issue_github_access_scope,
    validate_github_access_for_repo,
    verify_github_access_scope,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_repo_scoped_github_access_accepts_legacy_pat_and_checks_exact_target():
    token = "a" * 40
    captured = {}

    def opener(request, timeout=0):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse({"permissions": {"push": True}})

    result = validate_github_access_for_repo(
        token,
        owner="OuroborosCollective",
        repo="Wasd",
        opener=opener,
    )

    assert result.ok is True
    assert result.can_write is True
    assert result.code == "ready"
    assert captured["url"] == "https://api.github.com/repos/OuroborosCollective/Wasd"
    assert captured["authorization"] == f"Bearer {token}"
    assert captured["timeout"] == 30


def test_repo_scoped_github_access_maps_401_without_echoing_secret():
    token = "ghp_" + "b" * 40

    def opener(request, timeout=0):
        raise HTTPError(
            request.full_url,
            401,
            "Bad credentials",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"Bad credentials"}'),
        )

    result = validate_github_access_for_repo(
        token,
        owner="OuroborosCollective",
        repo="Wasd",
        opener=opener,
    )

    assert result.ok is False
    assert result.can_write is False
    assert result.code == "credential_rejected"
    assert token not in result.message


def test_repo_scoped_github_access_blocks_missing_effective_write_permission():
    token = "github_pat_" + "c" * 32

    result = validate_github_access_for_repo(
        token,
        owner="OuroborosCollective",
        repo="Wasd",
        opener=lambda request, timeout=0: FakeResponse({"permissions": {"pull": True}}),
    )

    assert result.ok is False
    assert result.can_write is False
    assert result.code == "write_permission_missing"


def test_server_issued_github_access_scope_is_user_and_revision_bound():
    secret = "s" * 32
    scope = issue_github_access_scope(
        user_id="user-1",
        repository="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        revision="a" * 40,
        secret=secret,
        now=1_000,
    )

    verified = verify_github_access_scope(scope, user_id="user-1", secret=secret, now=1_100)

    assert verified is not None
    assert (verified.owner, verified.repo, verified.branch, verified.revision) == (
        "OuroborosCollective", "Sovereign-Studio-ato", "main", "a" * 40,
    )
    assert verify_github_access_scope(scope, user_id="user-2", secret=secret, now=1_100) is None
    assert verify_github_access_scope(scope + "x", user_id="user-1", secret=secret, now=1_100) is None
    assert verify_github_access_scope(scope, user_id="user-1", secret=secret, now=1_601) is None


def test_repo_scoped_github_access_rejects_invalid_target_before_network():
    calls = []

    result = validate_github_access_for_repo(
        "ghp_" + "d" * 40,
        owner="OuroborosCollective/other",
        repo="Wasd",
        opener=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert result.ok is False
    assert result.code == "invalid_target"
    assert calls == []
