from pathlib import Path
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.job_store import (
    append_agent_projection,
    list_agent_evidence_anchors,
    list_agent_projections,
    read_latest_agent_github_draft_pr_readback,
)
from agent_runtime.fleet_supervisor import stable_hash


class _Cursor:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple]] = []
        self.one = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        self.queries.append((str(query), tuple(params)))

    def fetchone(self):
        return self.one

    def fetchall(self):
        return []


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.commit_count = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1


def test_projection_read_model_selects_newest_window_then_restores_chronology() -> None:
    conn = _Connection()

    assert list_agent_projections(conn, user_id="user-1", job_id="job-1", limit=100) == ()

    query, params = conn.cursor_instance.queries[-1]
    normalized = " ".join(query.split())
    assert "ORDER BY event.created_at DESC, event.id DESC LIMIT %s" in normalized
    assert "ORDER BY recent.created_at ASC, recent.id ASC" in normalized
    assert params == ("job-1", "user-1", 100)


def test_projection_store_rejects_retired_parallel_schema_before_database_write() -> None:
    conn = _Connection()
    with pytest.raises(ValueError, match="canonical visual projection"):
        append_agent_projection(
            conn,
            job_id="job-1",
            projection={
                "schemaVersion": "sovereign.live-workspace-projection.v1",
                "projectionId": "legacy-projection",
            },
        )
    assert conn.cursor_instance.queries == []
    assert conn.commit_count == 0


def test_evidence_anchor_read_model_uses_existing_owner_scoped_event_store() -> None:
    conn = _Connection()

    assert list_agent_evidence_anchors(conn, user_id="user-1", job_id="job-1", limit=500) == ()

    query, params = conn.cursor_instance.queries[-1]
    normalized = " ".join(query.split())
    assert "event.stage = 'live_workspace_evidence_anchor'" in normalized
    assert "JOIN sovereign_agent_jobs AS job ON job.job_id = event.job_id" in normalized
    assert params == ("job-1", "user-1", 200)


def test_persisted_github_publication_readback_is_owner_scoped_and_hash_validated() -> None:
    conn = _Connection()
    canonical = {
        "schemaVersion": "sovereign.github-draft-pr-readback.v1",
        "prUrl": "https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/2099",
        "prNumber": 2099,
        "headSha": "a" * 40,
        "publishedHeadSha": "a" * 40,
        "readbackHeadSha": "a" * 40,
        "draftVerified": True,
        "prStateVerified": "open",
        "readbackVerified": True,
        "checksReadbackVerified": True,
        "ciState": "pending",
        "checkRunCount": 0,
        "checksPendingCount": 0,
        "checksSuccessCount": 0,
        "checksFailureCount": 0,
        "statusContextCount": 0,
    }
    conn.cursor_instance.one = {
        "payload": {
            **canonical,
            "sourceHash": stable_hash(canonical),
            "authoritative": True,
        }
    }

    readback = read_latest_agent_github_draft_pr_readback(conn, user_id="user-1", job_id="job-1")

    assert readback is not None
    assert readback["jobId"] == "job-1"
    assert readback["sourceHash"] == stable_hash(canonical)
    query, params = conn.cursor_instance.queries[-1]
    normalized = " ".join(query.split())
    assert "event.stage = 'github_draft_pr_readback'" in normalized
    assert "JOIN sovereign_agent_jobs AS job ON job.job_id = event.job_id" in normalized
    assert params == ("job-1", "user-1")
