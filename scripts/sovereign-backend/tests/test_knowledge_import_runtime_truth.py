from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "scripts" / "sovereign-backend"
sys.path.insert(0, str(BACKEND))

flask_stub = ModuleType("flask")
flask_stub.jsonify = lambda value=None, **kwargs: value if value is not None else kwargs
flask_stub.request = SimpleNamespace()
sys.modules.setdefault("flask", flask_stub)

import knowledge_library


class FakeCursor:
    def __init__(self, *, fetchall=None, fetchone_sequence=None) -> None:
        self.executions: list[tuple[str, tuple | None]] = []
        self._fetchall = list(fetchall or [])
        self._fetchone_sequence = list(fetchone_sequence or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params=None) -> None:
        self.executions.append((sql, params))

    def fetchall(self):
        return list(self._fetchall)

    def fetchone(self):
        if not self._fetchone_sequence:
            raise AssertionError("unexpected fetchone")
        return self._fetchone_sequence.pop(0)


class FakeConnection:
    def __init__(self, cursors: list[FakeCursor]) -> None:
        self._cursors = list(cursors)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        if not self._cursors:
            raise AssertionError("unexpected cursor")
        return self._cursors.pop(0)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeGitHubResponse:
    def __init__(
        self,
        status_code: int,
        payload=None,
        *,
        headers=None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self.text = text

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_stale_zero_block_import_is_reconciled_fail_closed() -> None:
    cursor = FakeCursor(fetchall=[{"id": "source-1"}])
    conn = FakeConnection([cursor])

    count = knowledge_library._reconcile_stale_processing_sources(
        conn,
        "00000000-0000-0000-0000-000000000001",
    )

    assert count == 1
    assert conn.commits == 1
    sql, params = cursor.executions[0]
    assert "status='blocked'" in sql
    assert "knowledge_import_interrupted" in sql
    assert "status='processing'" in sql
    assert "NOT EXISTS" in sql
    assert params[1] == 15 * 60


def test_failed_import_updates_processing_source_without_storing_exception_message(monkeypatch) -> None:
    cursor = FakeCursor()
    conn = FakeConnection([cursor])
    document = knowledge_library.KnowledgeDocument(
        title="Broken PDF",
        text="bounded source text",
        source_type="pdf",
        source_url=None,
        metadata={},
    )
    raw_message = "secret-shaped internal parser detail"

    def fail(*args, **kwargs):
        raise ValueError(raw_message)

    monkeypatch.setattr(knowledge_library, "_insert_document_unchecked", fail)

    with pytest.raises(ValueError, match=raw_message):
        knowledge_library._insert_document(
            conn,
            "00000000-0000-0000-0000-000000000001",
            document,
        )

    assert conn.rollbacks == 1
    assert conn.commits == 1
    sql, params = cursor.executions[0]
    assert "status='blocked'" in sql
    assert params[0] == "knowledge_import_failed:ValueError"
    assert raw_message not in str(params)


def test_runtime_summary_requires_embeddings_and_link_integrity() -> None:
    cursor = FakeCursor(
        fetchone_sequence=[
            {
                "sources": 38,
                "ready_sources": 37,
                "partial_sources": 0,
                "processing_sources": 0,
                "blocked_sources": 1,
                "source_chunks": 400,
            },
            {
                "unique_blocks": 400,
                "embedded_blocks": 400,
                "missing_embeddings": 0,
            },
            {"orphan_links": 0},
        ]
    )
    conn = FakeConnection([cursor])

    summary = knowledge_library._knowledge_runtime_summary(
        conn,
        "00000000-0000-0000-0000-000000000001",
    )

    assert summary["importsUsable"] is True
    assert summary["embedded_blocks"] == summary["unique_blocks"] == 400
    assert summary["missing_embeddings"] == 0
    assert summary["orphan_links"] == 0
    assert summary["storage"] == "postgres-pgvector"


def test_admin_ui_exposes_import_and_vector_truth() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    assert "Import- und Vectorstatus" in app
    assert "reconciledStaleImports" in app
    assert "Fehlende Embeddings" in app
    assert "Verwaiste Links" in app
    assert "unterbrochener Import wurde fail-closed" in app


def test_github_public_repo_ignores_rejected_private_access(monkeypatch) -> None:
    monkeypatch.setenv("TOOLCHAIN_GITHUB_TOKEN", "rejected-test-token")
    calls = []
    responses = [
        FakeGitHubResponse(200, {"default_branch": "main"}),
        FakeGitHubResponse(200, {"sha": "tree-safe", "tree": []}),
    ]

    def fake_get(url, *, headers, timeout):
        calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        return responses.pop(0)

    monkeypatch.setattr(knowledge_library.requests, "get", fake_get)
    auth_state = {"authenticated": False}

    payload = knowledge_library._github_json(
        "/repos/OuroborosCollective/Sovereign-Studio-ato",
        auth_state=auth_state,
    )
    tree = knowledge_library._github_json(
        "/repos/OuroborosCollective/Sovereign-Studio-ato/git/trees/main?recursive=1",
        auth_state=auth_state,
    )

    assert payload["default_branch"] == "main"
    assert tree["sha"] == "tree-safe"
    assert auth_state["authenticated"] is False
    assert all("Authorization" not in call["headers"] for call in calls)


def test_github_private_repo_returns_permission_blocker_after_public_retry(monkeypatch) -> None:
    monkeypatch.setenv("TOOLCHAIN_GITHUB_TOKEN", "rejected-test-token")
    responses = [
        FakeGitHubResponse(404, {"message": "not found"}),
        FakeGitHubResponse(403, {"message": "forbidden"}),
    ]

    monkeypatch.setattr(
        knowledge_library.requests,
        "get",
        lambda *args, **kwargs: responses.pop(0),
    )

    with pytest.raises(knowledge_library.GitHubKnowledgeAccessError) as raised:
        knowledge_library._github_json("/repos/private-owner/private-repo")

    assert raised.value.blocker == "github_private_repo_access_required"
    assert raised.value.github_status == 403
    assert raised.value.response_status == 409
    assert "Token-/App-Berechtigung" in str(raised.value)


def test_github_rate_limit_is_not_misreported_as_repository_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("TOOLCHAIN_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    response = FakeGitHubResponse(
        403,
        {"message": "rate limit exceeded"},
        headers={"x-ratelimit-remaining": "0"},
    )
    monkeypatch.setattr(
        knowledge_library.requests,
        "get",
        lambda *args, **kwargs: response,
    )

    with pytest.raises(knowledge_library.GitHubKnowledgeAccessError) as raised:
        knowledge_library._github_json("/repos/public-owner/public-repo")

    assert raised.value.blocker == "github_rate_limit_exhausted"
    assert raised.value.response_status == 429


@pytest.mark.parametrize(
    ("exception", "blocker", "response_status"),
    [
        (
            knowledge_library.requests.Timeout("raw timeout detail with secret-value"),
            "github_api_timeout",
            504,
        ),
        (
            knowledge_library.requests.exceptions.SSLError("raw TLS detail with secret-value"),
            "github_tls_failure",
            502,
        ),
        (
            knowledge_library.requests.ConnectionError("raw DNS detail with secret-value"),
            "github_connection_unavailable",
            502,
        ),
        (
            knowledge_library.requests.RequestException("raw transport detail with secret-value"),
            "github_transport_error",
            502,
        ),
    ],
)
def test_github_transport_failures_return_bounded_safe_blockers(
    monkeypatch,
    exception,
    blocker,
    response_status,
) -> None:
    monkeypatch.setattr(
        knowledge_library.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(exception),
    )

    with pytest.raises(knowledge_library.GitHubKnowledgeAccessError) as raised:
        knowledge_library._github_json("/repos/public-owner/public-repo")

    assert raised.value.blocker == blocker
    assert raised.value.github_status is None
    assert raised.value.response_status == response_status
    assert "HTTPS/443" in str(raised.value)
    assert "secret-value" not in str(raised.value)


def test_github_import_failure_audit_is_bounded_and_url_fingerprinted() -> None:
    recorded = []
    raw_url = "https://github.com/private-owner/private-repo?token=secret-value"
    error = knowledge_library.GitHubKnowledgeAccessError(
        "safe operator message",
        blocker="github_connection_unavailable",
        response_status=502,
    )

    def record(action, target_id, changes):
        recorded.append({"action": action, "target_id": target_id, "changes": changes})

    correlation_id, audit_recorded = knowledge_library._record_github_import_failure(
        record,
        raw_url,
        error,
    )

    assert audit_recorded is True
    assert str(knowledge_library.uuid.UUID(correlation_id)) == correlation_id
    assert len(recorded) == 1
    evidence = recorded[0]
    assert evidence["action"] == "knowledge:github_import_failed"
    assert evidence["target_id"].startswith("github:")
    assert evidence["changes"] == {
        "result": "blocked",
        "blocker": "github_connection_unavailable",
        "githubHttpStatus": None,
        "transportFailure": True,
        "correlationId": correlation_id,
    }
    assert "private-owner" not in str(evidence)
    assert "secret-value" not in str(evidence)


def test_canonical_backend_wires_knowledge_failure_audit() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    assert "audit_event=audit" in app


def test_knowledge_runtime_mirror_remains_byte_equal() -> None:
    assert (BACKEND / "knowledge_library.py").read_bytes() == (
        ROOT / "backend" / "knowledge_library.py"
    ).read_bytes()
