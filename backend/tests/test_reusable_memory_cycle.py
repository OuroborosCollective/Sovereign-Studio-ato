from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from agent_runtime import reusable_memory


class FakeCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return [
            {
                "memoryKind": "experience",
                "memoryId": "candidate-1",
                "authority": "accepted-runtime-evidence",
                "similarity": 0.9,
            },
            {
                "memoryKind": "reference",
                "memoryId": "candidate-2",
                "authority": "reference-candidate",
                "similarity": 0.8,
            },
        ]


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self):
        return self.cursor_instance


def test_search_reusable_memory_keeps_reference_and_experience_authority_separate(monkeypatch) -> None:
    monkeypatch.setattr(
        reusable_memory,
        "embed_texts",
        lambda _texts: SimpleNamespace(
            vectors=[tuple(0.1 for _ in range(768))],
            model="test-embedding",
        ),
    )
    monkeypatch.setattr(reusable_memory, "vector_literal", lambda _vector: "[0.1]")
    conn = FakeConnection()

    result = reusable_memory.search_reusable_memory(
        conn,
        user_id="00000000-0000-0000-0000-000000000001",
        query_text="reuse this knowledge",
        limit=8,
    )

    assert result["ok"] is True
    assert result["canonicalStorage"] == "postgres-pgvector"
    assert result["indexProjection"] == "milvus-outbox"
    assert [row["authority"] for row in result["results"]] == [
        "accepted-runtime-evidence",
        "reference-candidate",
    ]
    assert "sovereign_agent_pattern_vectors" in conn.cursor_instance.sql
    assert "knowledge_learning_candidates" in conn.cursor_instance.sql
    assert "knowledge_blocks" in conn.cursor_instance.sql
    assert conn.cursor_instance.params[-1] == 8


def test_ouroboros_migration_keeps_pgvector_canonical_and_milvus_projected() -> None:
    migration = (ROOT / "scripts/sovereign-backend/migrations/023_ouroboros_memory_cycle.sql").read_text()

    assert "knowledge_learning_candidates" in migration
    assert "vector_index_outbox" in migration
    assert "canonical_store = 'postgres-pgvector'" in migration
    assert "target_index TEXT NOT NULL DEFAULT 'milvus'" in migration
    assert "reference-candidate" not in migration  # authority stays runtime provenance, not a DB decision shortcut
