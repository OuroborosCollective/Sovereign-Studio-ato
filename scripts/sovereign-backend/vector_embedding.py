"""Shared, fail-closed text embedding adapter for Sovereign memory systems.

The adapter never fabricates vectors. It either returns real 768-dimensional
vectors from Cloudflare Workers AI / a configured compatible proxy, or raises a
clear blocker. Secrets stay server-side and are never included in return values.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from typing import Any, Iterable

import requests

EMBEDDING_MODEL = os.getenv(
    "SOVEREIGN_EMBEDDING_MODEL",
    "@cf/google/embeddinggemma-300m",
).strip()
EMBEDDING_DIMENSIONS = 768
EMBEDDING_TIMEOUT_SECONDS = 30
MAX_EMBEDDING_INPUTS = 32
MAX_EMBEDDING_TEXT_CHARS = 8_000
DEFAULT_WORKER_AI_PROXY_URL = (
    "https://sovereign-llm-proxy.projectouroboroscollective.workers.dev"
)


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


def _direct_cloudflare_request(texts: list[str]) -> EmbeddingBatch | None:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not api_token:
        return None

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account_id}/ai/run/{EMBEDDING_MODEL}"
    )
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    gateway_id = os.getenv("AI_GATEWAY_ID", "").strip()
    if gateway_id:
        headers["cf-aig-gateway-id"] = gateway_id

    response = requests.post(
        url,
        headers=headers,
        json={"text": texts},
        timeout=EMBEDDING_TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise EmbeddingUnavailable(f"Cloudflare embedding route returned HTTP {response.status_code}")
    vectors = _extract_vectors(response.json())
    if len(vectors) != len(texts):
        raise EmbeddingUnavailable("Cloudflare embedding count did not match input count")
    return EmbeddingBatch(model=EMBEDDING_MODEL, vectors=vectors, provider="cloudflare-rest")


def _proxy_request(texts: list[str]) -> EmbeddingBatch | None:
    # Use the same organization-controlled Worker that already serves the live
    # LLM bridge when no deployment-specific embedding URL is configured. An
    # explicit empty WORKER_AI_PROXY_URL still disables this default fail-closed.
    configured_worker = os.getenv("WORKER_AI_PROXY_URL")
    base = (
        os.getenv("KNOWLEDGE_EMBEDDING_BASE_URL", "").strip()
        or (
            DEFAULT_WORKER_AI_PROXY_URL
            if configured_worker is None
            else configured_worker.strip()
        )
    ).rstrip("/")
    if not base:
        return None

    headers = {"Content-Type": "application/json"}
    proxy_key = os.getenv("WORKER_AI_PROXY_KEY", "").strip()
    if proxy_key:
        headers["Authorization"] = f"Bearer {proxy_key}"

    response = requests.post(
        f"{base}/v1/embeddings",
        headers=headers,
        json={"model": EMBEDDING_MODEL, "input": texts},
        timeout=EMBEDDING_TIMEOUT_SECONDS,
    )
    if not response.ok:
        if response.status_code == 404:
            worker_version = "unknown"
            embedding_path = "missing"
            try:
                health_response = requests.get(
                    f"{base}/health",
                    headers=headers,
                    timeout=EMBEDDING_TIMEOUT_SECONDS,
                )
                if health_response.ok:
                    health = health_response.json()
                    if isinstance(health, dict):
                        worker_version = str(health.get("version") or "unknown")[:40]
                        embedding_path = str(health.get("embeddingPath") or "missing")[:80]
            except (requests.RequestException, ValueError):
                pass
            raise EmbeddingUnavailable(
                "Embedding proxy route /v1/embeddings returned HTTP 404; "
                f"deployed worker version={worker_version}, embeddingPath={embedding_path}. "
                "Deploy the verified Worker embedding contract version 1.2.0 or newer."
            )
        raise EmbeddingUnavailable(f"Embedding proxy returned HTTP {response.status_code}")
    vectors = _extract_vectors(response.json())
    if len(vectors) != len(texts):
        raise EmbeddingUnavailable("Embedding proxy count did not match input count")
    return EmbeddingBatch(model=EMBEDDING_MODEL, vectors=vectors, provider="embedding-proxy")


def embed_texts(values: Iterable[str]) -> EmbeddingBatch:
    texts = _clean_texts(values)
    errors: list[str] = []

    for requester in (_direct_cloudflare_request, _proxy_request):
        try:
            result = requester(texts)
            if result is not None:
                return result
        except (requests.RequestException, ValueError, EmbeddingUnavailable) as exc:
            errors.append(str(exc)[:240])

    detail = " | ".join(errors) if errors else "no embedding route configured"
    raise EmbeddingUnavailable(f"Real embedding unavailable: {detail}")


def vector_literal(vector: Iterable[float]) -> str:
    normalized = _normalize_vector(list(vector))
    return "[" + ",".join(format(item, ".9g") for item in normalized) + "]"
