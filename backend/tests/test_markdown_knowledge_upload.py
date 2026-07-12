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


def test_markdown_upload_contract_is_visible_in_backend_and_both_surfaces() -> None:
    runtime_module = (BACKEND / "knowledge_library.py").read_text(encoding="utf-8")
    deploy_module = (DEPLOY / "knowledge_library.py").read_text(encoding="utf-8")
    user_panel = (ROOT / "src/features/knowledge/KnowledgeLibraryPanel.tsx").read_text(encoding="utf-8")
    backend_admin = (BACKEND / "app.py").read_text(encoding="utf-8")
    deploy_admin = (DEPLOY / "app.py").read_text(encoding="utf-8")

    assert runtime_module == deploy_module
    assert '_MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}' in runtime_module
    assert 'source_type = "markdown"' in runtime_module

    for surface in (user_panel, backend_admin, deploy_admin):
        assert "Markdown" in surface
        assert ".md" in surface
        assert ".markdown" in surface
        assert ".mdx" in surface
