"""VectorClient - read-only vector store access for grounded retrieval.

Element: VectorClient
Implements: ADR-007 §Decision; INV-SEC-001 (runtime corpus access is READ-ONLY);
  INV-SCOPE-006 (retrieval only when requires_grounding is true - enforced by
  RetrievalAdapter upstream); FR-RAG-001.

This module is the sole runtime path to the ``content_chunks`` corpus. It only
issues SELECT statements; the application connects with the ``app_runtime``
role which has SELECT-only grants on the corpus, so any write raises
permission-denied at the database (INV-SEC-001). It implements the
``RetrievalService`` port consumed by ``RetrievalAdapter``.

It is read-only by construction: there is no insert/update/delete method here,
and the SQL below is SELECT-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing only
    import psycopg_pool

from src.backend.contracts.ai_companion import (
    RetrievedChunk,
    RetrievalQuery,
    RetrievalUnavailableError,
)


class VectorClient:
    """Read-only pgvector-backed ``RetrievalService``.

    Implements: ADR-007; INV-SEC-001 (SELECT-only); FR-RAG-001.

    The caller supplies an already-open psycopg connection pool configured with
    the ``app_runtime`` DSN. Dimensions must match the active embedding model
    (``EMBEDDING_DIM``); a mismatch is an operational misconfiguration.
    """

    def __init__(self, pool: "psycopg_pool.ConnectionPool", *, embedding_dim: int = 1536) -> None:
        self._pool = pool
        self._embedding_dim = embedding_dim

    def search(self, query: RetrievalQuery) -> Sequence[RetrievedChunk]:
        """Return candidate chunks for a grounded query (published-only filter upstream).

        Implements: ADR-007 §Decision; INV-SCOPE-006. Read-only: SELECT only.

        Note: a real embedding vector for ``query.query`` must be produced by the
        embedding model before similarity search. Until the embedding adapter is
        wired, this method performs a filtered metadata lookup (language/level/
        topic) with a neutral score, which RetrievalAdapter then filters/ranks.
        This keeps retrieval read-only and deterministic without a provider call.
        """
        try:
            with self._pool.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT c.chunk_id, c.source_id, s.title, c.section, c.text,
                           s.language, s.level, s.topic, s.review_status
                    FROM content_chunks c
                    JOIN content_sources s ON s.source_id = c.source_id
                    WHERE s.language = %s
                      AND s.level = %s
                      AND (%s::text IS NULL OR s.topic = %s)
                    LIMIT %s
                    """,
                    (
                        query.language,
                        query.level,
                        query.topic,
                        query.topic,
                        max(query.top_k * 4, 20),
                    ),
                ).fetchall()
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RetrievalUnavailableError("vector store query failed") from exc

        chunks: list[RetrievedChunk] = []
        for row in rows:
            chunks.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    source_id=row["source_id"],
                    title=row["title"],
                    section=row["section"],
                    text=row["text"],
                    language=row["language"],
                    level=row["level"],
                    topic=row["topic"],
                    score=1.0,
                    review_status=row["review_status"],
                )
            )
        return chunks
