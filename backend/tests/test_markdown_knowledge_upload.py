from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DEPLOY = ROOT / "scripts" / "sovereign-backend"

sys.path.insert(0, str(BACKEND))

try:
    import flask  # noqa: F401
except ModuleNotFoundError:
    flask_stub = types.ModuleType("flask")
    flask_stub.jsonify = lambda *args, **kwargs: (args, kwargs)
    flask_stub.request = types.SimpleNamespace()
    sys.modules["flask"] = flask_stub

import knowledge_library


@pytest.mark.parametrize("filename", ["runtime.md", "runtime.markdown", "runtime.mdx"])
def test_markdown_upload_is_classified_and_preserves_heading_context(
    filename: str,
) -> None:
    payload = (
        "\ufeff# Runtime Truth\n\n"
        "Never fake success.\n\n"
        "## Markdown Upload\n\n"
        "The backend stores this document as searchable reference knowledge."
    ).encode("utf-8")

    source = knowledge_library.upload_document(filename=filename, payload=payload)

    assert source.source_type == "markdown"
    assert source.metadata == {
        "filename": filename,
        "extension": Path(filename).suffix.lower(),
        "format": "markdown",
    }
    assert "\ufeff" not in source.text
    chunks = knowledge_library.chunk_document(source.text)
    assert chunks
    assert {chunk.section_title for chunk in chunks} >= {
        "Runtime Truth",
        "Markdown Upload",
    }


def test_pdf_upload_limit_is_33_mib_while_non_pdf_limit_stays_bounded(monkeypatch) -> None:
    assert knowledge_library.MAX_UPLOAD_BYTES == 33 * 1024 * 1024
    assert knowledge_library.MAX_NON_PDF_UPLOAD_BYTES == 12 * 1024 * 1024
    assert knowledge_library._upload_limit_bytes("manual.pdf") == 33 * 1024 * 1024
    assert knowledge_library._upload_limit_bytes("manual.md") == 12 * 1024 * 1024

    expected = knowledge_library.KnowledgeDocument(
        source_type="pdf",
        title="manual.pdf",
        text="# Page 1\n\nverified",
        source_url=None,
        metadata={"filename": "manual.pdf", "pages": 1},
    )
    monkeypatch.setattr(knowledge_library, "_pdf_document", lambda filename, payload: expected)
    assert knowledge_library.upload_document(
        "manual.pdf",
        b"x" * knowledge_library.MAX_UPLOAD_BYTES,
    ) == expected

    with pytest.raises(ValueError, match="33 MB"):
        knowledge_library.upload_document(
            "manual.pdf",
            b"x" * (knowledge_library.MAX_UPLOAD_BYTES + 1),
        )
    with pytest.raises(ValueError, match="12 MB"):
        knowledge_library.upload_document(
            "manual.md",
            b"x" * (knowledge_library.MAX_NON_PDF_UPLOAD_BYTES + 1),
        )


def test_markdown_upload_contract_is_visible_in_backend_and_both_surfaces() -> None:
    runtime_module = (BACKEND / "knowledge_library.py").read_text(encoding="utf-8")
    deploy_module = (DEPLOY / "knowledge_library.py").read_text(encoding="utf-8")
    user_panel = (ROOT / "src/features/knowledge/KnowledgeLibraryPanel.tsx").read_text(encoding="utf-8")
    backend_admin = (BACKEND / "app.py").read_text(encoding="utf-8")
    deploy_admin = (DEPLOY / "app.py").read_text(encoding="utf-8")
    markdown_migration = (
        DEPLOY / "migrations/014_knowledge_source_markdown_type.sql"
    ).read_text(encoding="utf-8")

    assert runtime_module == deploy_module
    assert '_MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}' in runtime_module
    assert 'source_type = "markdown"' in runtime_module
    assert "knowledge_sources_source_type_check" in markdown_migration
    assert "'markdown'" in markdown_migration
    assert "NOT VALID" in markdown_migration
    assert "VALIDATE CONSTRAINT" in markdown_migration

    for surface in (user_panel, backend_admin, deploy_admin):
        assert "Markdown" in surface
        assert ".md" in surface
        assert ".markdown" in surface
        assert ".mdx" in surface
