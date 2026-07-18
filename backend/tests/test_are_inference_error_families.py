from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

flask_stub = ModuleType("flask")
flask_stub.jsonify = lambda value=None, **kwargs: value if value is not None else kwargs
flask_stub.request = SimpleNamespace()
sys.modules.setdefault("flask", flask_stub)
psycopg2_stub = ModuleType("psycopg2")
psycopg2_extras_stub = ModuleType("psycopg2.extras")
psycopg2_stub.extras = psycopg2_extras_stub
sys.modules.setdefault("psycopg2", psycopg2_stub)
sys.modules.setdefault("psycopg2.extras", psycopg2_extras_stub)

from are_inference import (
    KAPPA_SCALE,
    _quarantine_candidate,
    _similarity_kappa,
    canonical_json,
    deterministic_hash,
    evaluate_are_inference,
    repair_missing_knowledge_embeddings,
)
from knowledge_library import chunk_document, upload_document


class _NoopConnection:
    pass


def _knowledge_rows() -> list[dict[str, Any]]:
    return [
        {
            "blockId": "block-b",
            "contentSha256": "b" * 64,
            "sourceType": "pdf",
            "sourceTitle": "C++ Guide.pdf",
            "sectionTitle": "Page 2",
            "content": "RAII binds resource lifetime to object lifetime.",
            "similarity": 0.91,
        },
        {
            "blockId": "block-a",
            "contentSha256": "a" * 64,
            "sourceType": "github",
            "sourceTitle": "example/repo",
            "sectionTitle": "README",
            "content": "The project uses deterministic adapters.",
            "similarity": 0.91,
        },
    ]


def _experience_rows() -> dict[str, Any]:
    return {
        "ok": True,
        "results": [
            {
                "candidateId": "pattern-b",
                "patternText": "Compile before promotion.",
                "similarity": 0.93,
            },
            {
                "candidateId": "pattern-a",
                "patternText": "Keep reference and experience memory separate.",
                "similarity": 0.93,
            },
        ],
    }


def _evaluate(
    *,
    knowledge_rows: list[dict[str, Any]] | None = None,
    experience_rows: dict[str, Any] | None = None,
    online: bool = True,
    capabilities: list[str] | None = None,
    repository_hash: str = "f" * 64,
) -> dict[str, Any]:
    return evaluate_are_inference(
        _NoopConnection(),
        user_id="00000000-0000-0000-0000-000000000001",
        payload={
            "prompt": "Implement a deterministic C++ adapter",
            "onlineAvailable": online,
            "activeCapabilities": capabilities or [],
            "repository": {
                "owner": "OuroborosCollective",
                "repo": "Sovereign-Studio-ato",
                "branch": "main",
                "repositoryRevision": repository_hash,
                "evidenceComplete": True,
                "files": [
                    {"path": "src/z.ts", "objectId": "2" * 40},
                    {"path": "src/a.ts", "objectId": "1" * 40},
                ],
            },
        },
        knowledge_search=lambda *_args: list(knowledge_rows if knowledge_rows is not None else _knowledge_rows()),
        experience_search=lambda *_args, **_kwargs: dict(experience_rows if experience_rows is not None else _experience_rows()),
    )


def test_same_state_and_reordered_memory_produce_identical_result() -> None:
    first = _evaluate()
    second = _evaluate(
        knowledge_rows=list(reversed(_knowledge_rows())),
        experience_rows={"ok": True, "results": list(reversed(_experience_rows()["results"]))},
    )

    assert first["stateHash"] == second["stateHash"]
    assert first["adapter"] == second["adapter"]
    assert first["selectedKnowledgeIds"] == ["block-a", "block-b"]
    assert first["selectedPatternIds"] == ["pattern-a", "pattern-b"]
    assert first["state"]["repository"]["files"][0]["path"] == "src/a.ts"
    assert first["state"]["repository"]["evidenceComplete"] is True


def test_pdf_reference_is_used_but_never_relabelled_as_experience() -> None:
    result = _evaluate(experience_rows={"ok": True, "results": []})

    assert "block-b" in result["selectedKnowledgeIds"]
    assert result["selectedPatternIds"] == []
    assert "[REFERENCE:C++ Guide.pdf · Page 2]" in result["knowledgeContext"]
    assert "EVIDENCE-ACCEPTED EXPERIENCE" not in result["knowledgeContext"]
    assert result["adapter"] == "reference-memory-online"


def test_client_cannot_forge_local_synthesis_capability() -> None:
    online = _evaluate(online=True, capabilities=[])
    forged_local = _evaluate(online=False, capabilities=["local_code_synthesis"])

    assert online["decision"] == "online_required"
    assert forged_local["decision"] == "blocked"
    assert forged_local["adapter"] == "none"
    assert forged_local["state"]["activeCapabilities"] == []


def test_offline_without_local_synthesis_fails_closed_before_online_call() -> None:
    result = _evaluate(online=False, capabilities=[])

    assert result["decision"] == "blocked"
    assert result["adapter"] == "none"
    assert "offline_without_local_synthesis" in result["reasons"]


def test_memory_failures_are_reported_without_fabricated_context() -> None:
    def knowledge_failure(*_args: Any) -> list[dict[str, Any]]:
        raise RuntimeError("knowledge index unavailable")

    def experience_failure(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "blocker": "experience migration missing", "results": []}

    result = evaluate_are_inference(
        _NoopConnection(),
        user_id="00000000-0000-0000-0000-000000000001",
        payload={"prompt": "hello", "onlineAvailable": True},
        knowledge_search=knowledge_failure,
        experience_search=experience_failure,
    )

    assert result["decision"] == "online_required"
    assert result["knowledgeContext"] == ""
    assert result["experienceContext"] == ""
    assert result["blockers"]["knowledge"] == "knowledge index unavailable"
    assert result["blockers"]["experience"] == "experience migration missing"


def test_state_hash_changes_when_repository_truth_changes() -> None:
    first = _evaluate(repository_hash="a" * 64)
    second = _evaluate(repository_hash="b" * 64)

    assert first["stateHash"] != second["stateHash"]


def test_empty_prompt_is_rejected() -> None:
    with pytest.raises(ValueError, match="prompt is required"):
        evaluate_are_inference(
            _NoopConnection(),
            user_id="00000000-0000-0000-0000-000000000001",
            payload={"prompt": "   "},
            knowledge_search=lambda *_args: [],
            experience_search=lambda *_args, **_kwargs: {"ok": True, "results": []},
        )


def test_similarity_is_canonicalized_to_kappa_before_hashing() -> None:
    first = _evaluate(
        knowledge_rows=[{
            "blockId": "block-a",
            "contentSha256": "a" * 64,
            "content": "same evidence",
            "similarity": "0.9100009",
        }],
        experience_rows={"ok": True, "results": []},
    )
    second = _evaluate(
        knowledge_rows=[{
            "blockId": "block-a",
            "contentSha256": "a" * 64,
            "content": "same evidence",
            "similarity": 0.9100001,
        }],
        experience_rows={"ok": True, "results": []},
    )

    assert KAPPA_SCALE == 1_000_000
    assert first["stateHash"] == second["stateHash"]
    assert first["state"]["similarityScale"] == KAPPA_SCALE
    assert first["confidenceKappa"] == 910_000
    assert first["knowledgeConfidenceKappa"] == 910_000
    assert first["confidence"] == 0.91


def test_similarity_kappa_clamps_and_rejects_non_finite_values() -> None:
    assert _similarity_kappa({"similarity": "-0.1"}) == 0
    assert _similarity_kappa({"similarity": "1.5"}) == KAPPA_SCALE
    assert _similarity_kappa({"similarity": "NaN"}) == 0
    assert _similarity_kappa({"similarity": True}) == 0


def test_deterministic_state_rejects_floats() -> None:
    with pytest.raises(ValueError, match="floats are forbidden"):
        deterministic_hash({"confidence": 0.91})


def test_canonical_hash_is_stable_for_sets_and_key_order() -> None:
    first = {"tags": {"beta", "alpha"}, "nested": {"b": 2, "a": 1}}
    second = {"nested": {"a": 1, "b": 2}, "tags": {"alpha", "beta"}}

    assert canonical_json(first) == canonical_json(second)
    assert deterministic_hash(first) == deterministic_hash(second)


def test_pdf_upload_extracts_pages_and_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        def __init__(self, _stream: Any) -> None:
            self.pages = [
                FakePage("C++ ownership and RAII."),
                FakePage("Templates are instantiated deterministically."),
            ]

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))

    document = upload_document("cpp-guide.pdf", b"%PDF-test")
    chunks = chunk_document(document.text)

    assert document.source_type == "pdf"
    assert document.metadata["pages"] == 2
    assert "# Page 1" in document.text
    assert "# Page 2" in document.text
    assert len(chunks) == 2
    assert len({chunk.content_sha256 for chunk in chunks}) == 2


class _QuarantineCursor:
    def __init__(self) -> None:
        self.row: dict[str, Any] | None = None

    def __enter__(self) -> "_QuarantineCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, _query: str, params: tuple[Any, ...]) -> None:
        self.row = {
            "id": params[0],
            "status": "pending",
            "contentSha256": params[5],
        }

    def fetchone(self) -> dict[str, Any]:
        assert self.row is not None
        return self.row


class _QuarantineConnection:
    def __init__(self) -> None:
        self.cursor_instance = _QuarantineCursor()
        self.commits = 0

    def cursor(self) -> _QuarantineCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1


class _RepairCursor:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.row: dict[str, Any] | None = None
        self.updated_ids: list[str] = []
        self.rowcount = 0

    def __enter__(self) -> "_RepairCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        compact = " ".join(query.split())
        if compact.startswith("SELECT id::text, content"):
            self.rows = [
                {"id": "00000000-0000-0000-0000-000000000011", "content": "PDF page one", "contentSha256": "a" * 64},
                {"id": "00000000-0000-0000-0000-000000000012", "content": "PDF page two", "contentSha256": "b" * 64},
            ]
        elif compact.startswith("UPDATE knowledge_blocks"):
            self.updated_ids.append(str(params[2]))
            self.rowcount = 1
        elif compact.startswith("UPDATE knowledge_sources"):
            self.rowcount = 1
        elif compact.startswith("SELECT COUNT(*) AS remaining"):
            self.row = {"remaining": 0}
            self.rowcount = 1

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _RepairConnection:
    def __init__(self) -> None:
        self.cursor_instance = _RepairCursor()
        self.commits = 0

    def cursor(self) -> _RepairCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1


def test_event_driven_repair_recomputes_only_selected_missing_vectors() -> None:
    conn = _RepairConnection()
    vector = tuple([0.001] * 768)

    def provider(texts: Any) -> SimpleNamespace:
        values = list(texts)
        assert values == ["PDF page one", "PDF page two"]
        return SimpleNamespace(
            vectors=(vector, vector),
            provider="test-provider",
            model="test-embedding-model",
        )

    result = repair_missing_knowledge_embeddings(
        conn,
        user_id="00000000-0000-0000-0000-000000000001",
        limit=99,
        embedding_provider=provider,
    )

    assert result["selected"] == 2
    assert result["repaired"] == 2
    assert result["remaining"] == 0
    assert result["remainingForUser"] == 0
    assert result["provider"] == "test-provider"
    assert conn.cursor_instance.updated_ids == [
        "00000000-0000-0000-0000-000000000011",
        "00000000-0000-0000-0000-000000000012",
    ]
    assert conn.commits == 1


def test_quarantine_rejects_secret_like_material_before_database_write() -> None:
    conn = _QuarantineConnection()
    with pytest.raises(ValueError, match="secret-like material"):
        _quarantine_candidate(
            conn,
            user_id="00000000-0000-0000-0000-000000000001",
            body={
                "prompt": "Use this token",
                "response": "github_pat_EXAMPLESECRET123456789",
                "stateHash": "a" * 64,
                "adapter": "online-accelerator",
                "modelId": "provider/model",
            },
        )
    assert conn.commits == 0


def test_online_answer_is_quarantined_and_not_auto_promoted() -> None:
    first_conn = _QuarantineConnection()
    second_conn = _QuarantineConnection()
    body = {
        "prompt": "Create adapter",
        "response": "export const adapter = true;",
        "stateHash": "a" * 64,
        "adapter": "online-accelerator",
        "modelId": "provider/model",
    }

    first = _quarantine_candidate(first_conn, user_id="00000000-0000-0000-0000-000000000001", body=body)
    second = _quarantine_candidate(second_conn, user_id="00000000-0000-0000-0000-000000000001", body=body)

    assert first["quarantined"] is True
    assert first["promoted"] is False
    assert first["candidate"]["status"] == "pending"
    assert first["candidate"]["contentSha256"] == second["candidate"]["contentSha256"]
    assert first_conn.commits == 1


def test_low_similarity_rows_are_not_reported_as_selected_context() -> None:
    result = _evaluate(
        knowledge_rows=[{
            "blockId": "weak-block",
            "contentSha256": "c" * 64,
            "content": "weak match",
            "similarity": 0.2,
        }],
        experience_rows={"ok": True, "results": [{
            "candidateId": "weak-pattern",
            "patternText": "weak experience",
            "similarity": 0.3,
        }]},
    )
    assert result["selectedKnowledgeIds"] == []
    assert result["selectedPatternIds"] == []
    assert result["knowledgeContext"] == ""
    assert result["experienceContext"] == ""


def test_online_available_requires_literal_boolean_true() -> None:
    result = evaluate_are_inference(
        _NoopConnection(),
        user_id="00000000-0000-0000-0000-000000000001",
        payload={"prompt": "hello", "onlineAvailable": "false"},
        knowledge_search=lambda *_args: [],
        experience_search=lambda *_args, **_kwargs: {"ok": True, "results": []},
    )
    assert result["decision"] == "blocked"
