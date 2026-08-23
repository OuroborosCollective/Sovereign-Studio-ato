from pathlib import Path
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.job_store import append_agent_projection, list_agent_evidence_anchors, list_agent_projections


class _Cursor:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        self.queries.append((str(query), tuple(params)))

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
