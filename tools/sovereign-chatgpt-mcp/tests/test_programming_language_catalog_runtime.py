from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
MCP = ROOT / "tools" / "sovereign-chatgpt-mcp"
sys.path.insert(0, str(MCP))

import command_contract
import programming_language_catalog_runtime


REVISION = "a" * 40
DIGEST = "sha256:" + "b" * 64
TREE_SHA = "c" * 40
CONTENT_SHA = "d" * 64
SOURCE_ID = "11111111-2222-3333-4444-555555555555"


def verified_payload() -> dict:
    return {
        "ok": True,
        "status": "PROGRAMMING_LANGUAGE_CATALOG_PERSISTENT_IMPORT_VERIFIED",
        "sourceRevision": REVISION,
        "imageDigest": DIGEST,
        "catalog": {
            "catalogRevision": programming_language_catalog_runtime.CATALOG_REVISION,
            "commitSha": programming_language_catalog_runtime.CATALOG_REVISION,
            "treeSha": TREE_SHA,
            "sourceId": SOURCE_ID,
            "sourceUrl": "https://github.com/OuroborosCollective/ProgrammiersprachenMD/tree/" + programming_language_catalog_runtime.CATALOG_REVISION + "/knowledge",
            "title": programming_language_catalog_runtime.CATALOG_TITLE,
            "status": "ready",
            "contentSha256": CONTENT_SHA,
            "contentBytes": 1000,
            "chunkCount": 3,
            "linkedBlocks": 3,
            "embeddedBlocks": 3,
            "missingEmbeddings": 0,
            "learningCandidateCount": 3,
            "outboxCount": 3,
            "languageCount": 12,
            "bugfixObservationCount": 4,
            "authority": "curated-reference",
            "bugfixObservationAuthority": "unverified-reference-candidate",
            "sourcePinned": True,
            "embeddingModel": "real-model",
            "embeddingProviderPresent": True,
            "userAssignmentFingerprint": "f" * 24,
        },
        "http": {
            "firstImportStatus": 201,
            "firstImportDuplicate": False,
            "secondImportStatus": 200,
            "secondImportDuplicate": True,
            "knowledgeLibraryListStatus": 200,
            "knowledgeLibraryProjectionVisible": True,
        },
        "deduplication": {
            "sameSourceId": True,
            "sameContentSha256": True,
            "sourceRowsForUserAndContent": 1,
        },
        "mutationPerformed": True,
        "persistentMutation": True,
        "secretValuesReturned": False,
        "documentContentReturned": False,
    }


def test_embedded_persistent_import_script_is_valid_python() -> None:
    compile(
        programming_language_catalog_runtime._BACKEND_PERSISTENT_IMPORT_SCRIPT,
        "programming-language-catalog-runtime",
        "exec",
    )


def test_runtime_requires_owner_approval_and_exact_identity() -> None:
    runtime = programming_language_catalog_runtime.ProgrammingLanguageCatalogRuntime()
    with pytest.raises(ValueError, match="Owner-Freigabe"):
        runtime.persistent_import(
            expected_revision=REVISION,
            expected_image_digest=DIGEST,
            owner_approved=False,
        )
    with pytest.raises(ValueError, match="Commit-SHA"):
        runtime.persistent_import(
            expected_revision="main",
            expected_image_digest=DIGEST,
            owner_approved=True,
        )
    with pytest.raises(ValueError, match="sha256-Digest"):
        runtime.persistent_import(
            expected_revision=REVISION,
            expected_image_digest="latest",
            owner_approved=True,
        )


def test_success_requires_persistent_http_db_vector_and_dedupe_readback(monkeypatch) -> None:
    observed = {}
    payload = verified_payload()

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(programming_language_catalog_runtime.subprocess, "run", fake_run)
    result = programming_language_catalog_runtime.ProgrammingLanguageCatalogRuntime().persistent_import(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        owner_approved=True,
    )

    assert result == payload
    assert observed["argv"][-3:] == [
        REVISION,
        DIGEST,
        programming_language_catalog_runtime.CATALOG_REVISION,
    ]
    script = str(observed["input"])
    assert script.count("/api/admin/knowledge/catalogs/programming-languages/import") == 2
    assert 'request_json(\n        "POST",\n        "/api/admin/knowledge/catalogs/programming-languages/import"' in script
    assert 'request_json("GET", "/api/admin/knowledge/sources")' in script
    assert "knowledge_source_blocks" in script
    assert "knowledge_learning_candidates" in script
    assert "vector_index_outbox" in script
    assert "DELETE FROM knowledge_sources" not in script
    assert "ADMIN_API_KEY" in script
    assert "secretValuesReturned" in script


def test_incomplete_vector_or_projection_evidence_is_rejected(monkeypatch) -> None:
    payload = verified_payload()
    payload["catalog"]["embeddedBlocks"] = 2
    payload["http"]["knowledgeLibraryProjectionVisible"] = False
    monkeypatch.setattr(
        programming_language_catalog_runtime.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(payload) + "\n",
            stderr="",
        ),
    )

    result = programming_language_catalog_runtime.ProgrammingLanguageCatalogRuntime().persistent_import(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        owner_approved=True,
    )
    assert result["ok"] is False
    assert result["failureFamily"] == "PROGRAMMING_LANGUAGE_CATALOG_EVIDENCE_INCOMPLETE"


def test_failure_never_returns_stderr_or_document_content(monkeypatch) -> None:
    monkeypatch.setattr(
        programming_language_catalog_runtime.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            1,
            stdout='{"ok":false,"status":"PROGRAMMING_LANGUAGE_CATALOG_PERSISTENT_IMPORT_FAILED"}\n',
            stderr="raw secret-shaped admin failure",
        ),
    )
    result = programming_language_catalog_runtime.ProgrammingLanguageCatalogRuntime().persistent_import(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        owner_approved=True,
    )
    assert result["ok"] is False
    assert result["stderrType"] == "present"
    assert "raw secret-shaped" not in str(result)
    assert result["secretValuesReturned"] is False
    assert result["documentContentReturned"] is False


def test_persistent_import_is_host_worker_only_and_packaged() -> None:
    action = "programming_language_catalog_persistent_import"
    assert command_contract.is_mutating_action(action) is True

    server = (MCP / "server.py").read_text("utf-8")
    broker = (MCP / "broker.py").read_text("utf-8")
    dockerfile = (MCP / "Dockerfile").read_text("utf-8")
    installer = (MCP / "deploy" / "install-on-vps.sh").read_text("utf-8")

    assert "def programming_language_catalog_persistent_import(" in server
    assert f'"{action}"' in broker
    assert "programming_language_catalog_runtime.py" in dockerfile
    assert 'install -m 0640 "$SOURCE_DIR/programming_language_catalog_runtime.py"' in installer
    assert "import programming_language_catalog_runtime" in installer
    assert "callable(server.programming_language_catalog_persistent_import)" in installer
