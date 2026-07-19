"""Internal pgvector memory for validated Sovereign agent experience patterns."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from vector_embedding import EMBEDDING_MODEL, EmbeddingUnavailable, embed_texts, vector_literal


def pattern_text(result: Any) -> str:
    payload = result.payload if hasattr(result, "payload") else dict(result or {})
    structured = str(payload.get("embeddingText") or "").strip()
    if structured:
        return structured[:8_000]
    return "\n".join(
        part for part in (
            f"Kind: {payload.get('kind') or 'unknown'}",
            f"Mission: {payload.get('mission') or ''}",
            f"Changed files: {', '.join(payload.get('changedFiles') or [])}",
            f"Diff evidence: {payload.get('diffSummary') or ''}",
            f"Test evidence: {payload.get('testSummary') or ''}",
            f"Blocker: {payload.get('blocker') or ''}",
        ) if part.strip()
    )[:8_000]


def persist_pattern_vector(
    conn: Any,
    *,
    candidate_id: str,
    user_id: str,
    result: Any,
    commit: bool = True,
) -> dict[str, Any]:
    if not getattr(result, "allowed", False) or not getattr(result, "remote_memory_allowed", False):
        return {
            "stored": False,
            "storage": "postgres-pgvector",
            "reason": "pattern_not_accepted",
        }

    text = pattern_text(result)
    if not text.strip():
        return {
            "stored": False,
            "storage": "postgres-pgvector",
            "reason": "pattern_text_empty",
        }

    try:
        batch = embed_texts([text])
        value = vector_literal(batch.vectors[0])
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO sovereign_agent_pattern_vectors
                   (candidate_id, user_id, pattern_text, embedding, embedding_model)
                   VALUES (%s, %s, %s, %s::vector, %s)
                   ON CONFLICT (candidate_id) DO UPDATE SET
                       pattern_text=EXCLUDED.pattern_text,
                       embedding=EXCLUDED.embedding,
                       embedding_model=EXCLUDED.embedding_model""",
                (candidate_id, user_id, text, value, batch.model),
            )
            cur.execute(
                """INSERT INTO vector_index_outbox
                   (user_id, entity_type, entity_id, content_sha256, embedding_model)
                   VALUES (%s, 'agent_pattern', %s, %s, %s)
                   ON CONFLICT (target_index, entity_type, entity_id, content_sha256, embedding_model)
                   DO UPDATE SET status=CASE
                       WHEN vector_index_outbox.status='indexed' THEN 'indexed'
                       ELSE 'pending'
                   END, updated_at=NOW(), last_error=NULL""",
                (
                    user_id,
                    candidate_id,
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    batch.model,
                ),
            )
        if commit:
            conn.commit()
        return {
            "stored": True,
            "storage": "postgres-pgvector",
            "candidateId": candidate_id,
            "embeddingModel": batch.model,
            "provider": batch.provider,
        }
    except EmbeddingUnavailable as exc:
        conn.rollback()
        return {
            "stored": False,
            "storage": "postgres-pgvector",
            "candidateId": candidate_id,
            "reason": "embedding_unavailable",
            "blocker": str(exc)[:500],
        }
    except Exception as exc:
        conn.rollback()
        return {
            "stored": False,
            "storage": "postgres-pgvector",
            "candidateId": candidate_id,
            "reason": "vector_storage_unavailable",
            "blocker": str(exc)[:500],
        }


def search_pattern_vectors(
    conn: Any,
    *,
    user_id: str,
    query_text: str,
    limit: int = 8,
) -> dict[str, Any]:
    clean = str(query_text or "").strip()[:4_000]
    if not clean:
        raise ValueError("query is required")
    bounded_limit = max(1, min(int(limit), 20))
    try:
        batch = embed_texts([clean])
        value = vector_literal(batch.vectors[0])
        with conn.cursor() as cur:
            cur.execute(
                """SELECT v.candidate_id AS "candidateId", c.kind, c.summary,
                          c.payload, c.predictive_signal AS "predictiveSignal",
                          v.pattern_text AS "patternText",
                          1 - (v.embedding <=> %s::vector) AS similarity
                   FROM sovereign_agent_pattern_vectors v
                   JOIN sovereign_agent_pattern_candidates c
                     ON c.candidate_id=v.candidate_id
                   WHERE v.user_id=%s AND c.decision='accepted'
                   ORDER BY v.embedding <=> %s::vector,
                            v.candidate_id ASC
                   LIMIT %s""",
                (value, user_id, value, bounded_limit),
            )
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "ok": True,
            "results": rows,
            "count": len(rows),
            "storage": "postgres-pgvector",
            "embeddingModel": batch.model,
        }
    except EmbeddingUnavailable as exc:
        return {
            "ok": False,
            "results": [],
            "count": 0,
            "storage": "postgres-pgvector",
            "reason": "embedding_unavailable",
            "blocker": str(exc)[:500],
        }
    except Exception as exc:
        return {
            "ok": False,
            "results": [],
            "count": 0,
            "storage": "postgres-pgvector",
            "reason": "vector_search_unavailable",
            "blocker": str(exc)[:500],
        }
