"""Shared fail-closed text embedding adapter for Sovereign memory systems.

Embeddings use the same private FreeLLMAPI Docker runtime as the free chat
revolver. The adapter never fabricates vectors and never falls back to the
retired Cloudflare Worker path. Protected unified-key material stays server-side
and is zeroed from its mutable read buffer after every request.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
from typing import Any, Iterable

import requests

from free_revolver_provider_contracts import (
    ManagedKeyContractError,
    normalize_api_base,
    read_managed_freellm_key_file,
)

EMBEDDING_MODEL = os.getenv(
    "SOVEREIGN_EMBEDDING_MODEL",
    "gemini-embedding-001",
).strip()
EMBEDDING_DIMENSIONS = 768
EMBEDDING_TIMEOUT_SECONDS = 30
MAX_EMBEDDING_INPUTS = 32
MAX_EMBEDDING_TEXT_CHARS = 8_000
DEFAULT_FREELLMAPI_BASE_URL = "http://freellmapi:3001/v1"
DEFAULT_OWNER_INPUT_ROOT = Path("/opt/sovereign-owner-managed")
DEFAULT_FREELLMAPI_KEY_FILENAME = "freellmapi_unified_key.txt"


class EmbeddingUnavailable(RuntimeError):
    """Raised when no real embedding route can complete the request."""


@dataclass(frozen=True)
class EmbeddingBatch:
    model: str
    vectors: tuple[tuple[float, ...], ...]
    provider: str


def _clean_texts(values: Iterable[str]) -> list[str]:
    texts = [str(value or "").strip()[:MAX_EMBEDDING_TEXT_CHARS] for value in values]
    texts = [value for value in texts if value]
    if not texts:
        raise ValueError("At least one non-empty text is required for embedding")
    if len(texts) > MAX_EMBEDDING_INPUTS:
        raise ValueError(f"At most {MAX_EMBEDDING_INPUTS} texts may be embedded per request")
    return texts


def _normalize_vector(value: Any) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)):
        raise EmbeddingUnavailable("Embedding provider returned a non-array vector")
    vector = tuple(float(item) for item in value)
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise EmbeddingUnavailable(
            f"Embedding provider returned {len(vector)} dimensions; expected {EMBEDDING_DIMENSIONS}"
        )
    if any(not math.isfinite(item) for item in vector):
        raise EmbeddingUnavailable("Embedding provider returned non-finite values")
    return vector


def _extract_vectors(payload: Any) -> tuple[tuple[float, ...], ...]:
    if not isinstance(payload, dict):
        raise EmbeddingUnavailable("Embedding provider returned an invalid payload")

    # OpenAI-compatible: {"data": [{"embedding": [...]}, ...]}
    data = payload.get("data")
    if isinstance(data, list) and data:
        if all(isinstance(item, dict) and "embedding" in item for item in data):
            return tuple(_normalize_vector(item["embedding"]) for item in data)
        if all(isinstance(item, (list, tuple)) for item in data):
            return tuple(_normalize_vector(item) for item in data)

    # Cloudflare REST: {"result": {"data": [[...], ...]}}
    result = payload.get("result")
    if isinstance(result, dict):
        nested = result.get("data") or result.get("embeddings")
        if isinstance(nested, list) and nested:
            if all(isinstance(item, dict) and "embedding" in item for item in nested):
                return tuple(_normalize_vector(item["embedding"]) for item in nested)
            if all(isinstance(item, (list, tuple)) for item in nested):
                return tuple(_normalize_vector(item) for item in nested)

    # Some compatible proxies use {"embeddings": [[...], ...]}.
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        return tuple(_normalize_vector(item) for item in embeddings)

    raise EmbeddingUnavailable("Embedding provider response contained no usable vectors")


def _freellm_request(texts: list[str]) -> EmbeddingBatch:
    configured_base = os.getenv(
        "FREELLMAPI_INTERNAL_URL",
        DEFAULT_FREELLMAPI_BASE_URL,
    ).strip()
    try:
        base = normalize_api_base(configured_base)
    except ValueError as exc:
        raise EmbeddingUnavailable("FreeLLMAPI embedding base is invalid") from exc
    if base != DEFAULT_FREELLMAPI_BASE_URL:
        raise EmbeddingUnavailable(
            "Embeddings require the private FreeLLMAPI Docker endpoint"
        )

    owner_root = Path(
        os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", str(DEFAULT_OWNER_INPUT_ROOT))
    ).resolve()
    configured_key_path = os.getenv(
        "SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE",
        str(owner_root / DEFAULT_FREELLMAPI_KEY_FILENAME),
    ).strip()
    protected = bytearray()
    try:
        protected, unified_key = read_managed_freellm_key_file(
            owner_root=owner_root,
            configured_path=configured_key_path,
            expected_filename=DEFAULT_FREELLMAPI_KEY_FILENAME,
            error_prefix="freellm",
        )
        response = requests.post(
            f"{base}/embeddings",
            headers={
                "Authorization": f"Bearer {unified_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": texts,
                "dimensions": EMBEDDING_DIMENSIONS,
            },
            timeout=EMBEDDING_TIMEOUT_SECONDS,
        )
    except ManagedKeyContractError as exc:
        raise EmbeddingUnavailable(f"FreeLLMAPI unified key unavailable: {exc.code}") from exc
    finally:
        for index in range(len(protected)):
            protected[index] = 0

    if not response.ok:
        raise EmbeddingUnavailable(
            f"FreeLLMAPI embedding route returned HTTP {response.status_code}"
        )
    payload = response.json()
    vectors = _extract_vectors(payload)
    if len(vectors) != len(texts):
        raise EmbeddingUnavailable("FreeLLMAPI embedding count did not match input count")
    response_model = (
        str(payload.get("model") or EMBEDDING_MODEL).strip()
        if isinstance(payload, dict)
        else EMBEDDING_MODEL
    )
    return EmbeddingBatch(
        model=response_model or EMBEDDING_MODEL,
        vectors=vectors,
        provider="freellmapi-private",
    )


def embed_texts(values: Iterable[str]) -> EmbeddingBatch:
    texts = _clean_texts(values)
    errors: list[str] = []

    for requester in (_freellm_request,):
        try:
            return requester(texts)
        except (requests.RequestException, ValueError, EmbeddingUnavailable) as exc:
            errors.append(str(exc)[:240])

    detail = " | ".join(errors) if errors else "no embedding route configured"
    raise EmbeddingUnavailable(f"Real embedding unavailable: {detail}")


def vector_literal(vector: Iterable[float]) -> str:
    normalized = _normalize_vector(list(vector))
    return "[" + ",".join(format(item, ".9g") for item in normalized) + "]"
