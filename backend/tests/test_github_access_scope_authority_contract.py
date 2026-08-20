"""Fail-closed evidence tests for server-issued GitHub access scopes.

The scope is an authority artifact, not a client hint.  These tests bind the
signature to a user, an exact repository revision and one declared purpose;
they also keep the canonical and deployment implementations byte-identical.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.github_access import (  # noqa: E402
    issue_github_access_scope,
    verify_github_access_scope,
)


REPOSITORY = "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
REVISION = "a" * 40
PURPOSE = "github-access-validate"
SECRET = "authority-contract-test-secret"


def _scope() -> str:
    return issue_github_access_scope(
        user_id="owner-42",
        repository=REPOSITORY,
        branch="main",
        revision=REVISION,
        purpose=PURPOSE,
        secret=SECRET,
        now=10_000,
    )


def test_server_scope_is_bound_to_user_repository_revision_and_purpose() -> None:
    scope = _scope()

    verified = verify_github_access_scope(
        scope,
        user_id="owner-42",
        purpose=PURPOSE,
        secret=SECRET,
        now=10_001,
    )

    assert verified is not None
    assert (verified.owner, verified.repo, verified.branch, verified.revision, verified.purpose) == (
        "OuroborosCollective",
        "Sovereign-Studio-ato",
        "main",
        REVISION,
        PURPOSE,
    )


def test_server_scope_fails_closed_for_foreign_user_purpose_or_expiry() -> None:
    scope = _scope()

    assert verify_github_access_scope(
        scope,
        user_id="other-user",
        purpose=PURPOSE,
        secret=SECRET,
        now=10_001,
    ) is None
    assert verify_github_access_scope(
        scope,
        user_id="owner-42",
        purpose="github-pr-merge",
        secret=SECRET,
        now=10_001,
    ) is None
    assert verify_github_access_scope(
        scope,
        user_id="owner-42",
        purpose=PURPOSE,
        secret=SECRET,
        now=10_601,
    ) is None


def test_scope_issuer_rejects_missing_startup_secret_and_invalid_purpose() -> None:
    with pytest.raises(RuntimeError, match="github_access_scope_secret_unavailable"):
        issue_github_access_scope(
            user_id="owner-42",
            repository=REPOSITORY,
            branch="main",
            revision=REVISION,
            purpose=PURPOSE,
            secret="",
            now=10_000,
        )

    with pytest.raises(ValueError, match="github_access_scope_purpose_invalid"):
        issue_github_access_scope(
            user_id="owner-42",
            repository=REPOSITORY,
            branch="main",
            revision=REVISION,
            purpose="merge with spaces",
            secret=SECRET,
            now=10_000,
        )


def test_validate_route_uses_only_the_server_issued_target_and_fixed_purpose() -> None:
    route_source = (BACKEND / "agent_runtime" / "routes.py").read_text("utf-8")
    validation_start = route_source.index('    @app.route("/api/user/agent/github-access/validate", methods=["POST"])')
    validation_end = route_source.index('    @app.route("/api/user/agent/validate-mission", methods=["POST"])')
    validation_route = route_source[validation_start:validation_end]

    assert 'purpose="github-access-validate"' in validation_route
    assert "target = (scope.owner, scope.repo) if scope else None" in validation_route
    assert 'body.get("repository")' not in validation_route
    assert 'body.get("repoUrl")' not in validation_route


def test_authority_runtime_mirror_is_byte_identical() -> None:
    canonical = BACKEND / "agent_runtime" / "github_access.py"
    deployment_mirror = ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "github_access.py"

    assert canonical.read_bytes() == deployment_mirror.read_bytes()


def test_authority_route_mirror_is_byte_identical() -> None:
    canonical = BACKEND / "agent_runtime" / "routes.py"
    deployment_mirror = ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "routes.py"

    assert canonical.read_bytes() == deployment_mirror.read_bytes()
