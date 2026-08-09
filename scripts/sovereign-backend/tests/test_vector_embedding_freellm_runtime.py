from __future__ import annotations

from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import vector_embedding


class _EmbeddingResponse:
    ok = True
    status_code = 200

    def json(self):
        return {
            "object": "list",
            "model": "gemini-embedding-001",
            "data": [{"embedding": [0.125] * vector_embedding.EMBEDDING_DIMENSIONS}],
        }


def test_embeddings_use_private_freellmapi_with_768_dimensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "freellmapi-" + ("a" * 48)
    key_path = tmp_path / "freellmapi_unified_key.txt"
    key_path.write_text(key + "\n", encoding="utf-8")
    key_path.chmod(0o600)

    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE", str(key_path))
    monkeypatch.setenv("FREELLMAPI_INTERNAL_URL", "http://freellmapi:3001/v1")

    observed: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout):
        observed.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _EmbeddingResponse()

    monkeypatch.setattr(vector_embedding.requests, "post", fake_post)

    batch = vector_embedding.embed_texts(["Sovereign memory evidence"])

    assert observed["url"] == "http://freellmapi:3001/v1/embeddings"
    assert observed["json"] == {
        "model": vector_embedding.EMBEDDING_MODEL,
        "input": ["Sovereign memory evidence"],
        "dimensions": 768,
    }
    assert observed["headers"] == {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    assert batch.provider == "freellmapi-private"
    assert batch.model == "gemini-embedding-001"
    assert len(batch.vectors) == 1
    assert len(batch.vectors[0]) == 768


def test_embedding_adapter_has_no_cloudflare_runtime_fallback() -> None:
    source = (BACKEND / "vector_embedding.py").read_text("utf-8")

    assert "DEFAULT_WORKER_AI_PROXY_URL" not in source
    assert "CLOUDFLARE_ACCOUNT_ID" not in source
    assert "CLOUDFLARE_API_TOKEN" not in source
    assert "WORKER_AI_PROXY_URL" not in source
    assert "http://freellmapi:3001/v1" in source
    assert '"dimensions": EMBEDDING_DIMENSIONS' in source
