"""Unified read path over canonical reference and accepted experience memory."""

from __future__ import annotations

from typing import Any

from vector_embedding import EmbeddingUnavailable, embed_texts, vector_literal


def search_reusable_memory(
    conn: Any,
    *,
    user_id: str,
    query_text: str,
    limit: int = 8,
) -> dict[str, Any]:
    """Search both memory classes without collapsing their authority levels."""
    clean = str(query_text or "").strip()[:4_000]
    if not clean:
        raise ValueError("query is required")
    bounded_limit = max(1, min(int(limit), 20))
    try:
        batch = embed_texts([clean])
        value = vector_literal(batch.vectors[0])
        with conn.cursor() as cur:
            cur.execute(
                """WITH reusable_memory AS (
                       SELECT 'experience'::text AS memory_kind,
                              v.candidate_id::text AS memory_id,
                              c.kind::text AS title,
                              c.summary::text AS summary,
                              v.pattern_text::text AS content,
                              c.payload AS provenance,
                              'accepted-runtime-evidence'::text AS authority,
                              v.embedding <=> %s::vector AS distance
                       FROM sovereign_agent_pattern_vectors v
                       JOIN sovereign_agent_pattern_candidates c
                         ON c.candidate_id=v.candidate_id
                       WHERE v.user_id=%s AND c.decision='accepted'
                       UNION ALL
                       SELECT 'reference'::text AS memory_kind,
                              k.candidate_id::text AS memory_id,
                              s.title::text AS title,
                              k.summary::text AS summary,
                              b.content::text AS content,
                              k.provenance AS provenance,
                              'reference-candidate'::text AS authority,
                              b.embedding <=> %s::vector AS distance
                       FROM knowledge_learning_candidates k
                       JOIN knowledge_blocks b ON b.id=k.block_id
                       JOIN knowledge_sources s ON s.id=k.source_id
                       WHERE k.user_id=%s::uuid
                         AND k.status='candidate'
                         AND b.embedding IS NOT NULL
                         AND s.status IN ('ready','partial')
                   )
                   SELECT memory_kind AS "memoryKind",
                          memory_id AS "memoryId",
                          title,
                          summary,
                          content,
                          provenance,
                          authority,
                          1 - distance AS similarity
                   FROM reusable_memory
                   ORDER BY distance ASC, memory_kind ASC, memory_id ASC
                   LIMIT %s""",
                (value, user_id, value, user_id, bounded_limit),
            )
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "ok": True,
            "results": rows,
            "count": len(rows),
            "canonicalStorage": "postgres-pgvector",
            "indexProjection": "milvus-outbox",
            "embeddingModel": batch.model,
        }
    except EmbeddingUnavailable as exc:
        return {
            "ok": False,
            "results": [],
            "count": 0,
            "canonicalStorage": "postgres-pgvector",
            "indexProjection": "milvus-outbox",
            "reason": "embedding_unavailable",
            "blocker": str(exc)[:500],
        }
    except Exception as exc:
        return {
            "ok": False,
            "results": [],
            "count": 0,
            "canonicalStorage": "postgres-pgvector",
            "indexProjection": "milvus-outbox",
            "reason": "reusable_memory_search_unavailable",
            "blocker": str(exc)[:500],
        }
