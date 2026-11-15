"""RetrievalAdapter - conditional, published-only retrieval over an injected port.

Element: RetrievalAdapter
Implements: ADR-007 §Decision/§Ingestion flow step 4; INV-SCOPE-006.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.contracts.ai_companion import (
    CEFR_LEVELS,
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    LANGUAGE_ENGLISH,
    MAX_TOP_K,
    EvidenceSet,
    InvalidRequestError,
    RetrievedChunk,
    RetrievalQuery,
    RetrievalService,
    RetrievalUnavailableError,
)


@dataclass(frozen=True)
class RetrievalConfig:
    """ADR-007 / configuration governance: deterministic retrieval bounds."""

    default_top_k: int = DEFAULT_TOP_K
    max_top_k: int = MAX_TOP_K
    min_score: float = DEFAULT_MIN_SCORE

    def __post_init__(self) -> None:
        if not 1 <= self.max_top_k <= MAX_TOP_K:
            raise ValueError("max_top_k must be between 1 and 10")
        if not 1 <= self.default_top_k <= self.max_top_k:
            raise ValueError("default_top_k must be within 1..max_top_k")
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError("min_score must be between 0.0 and 1.0")


class RetrievalAdapter:
    """ADR-007: enforce publication, filters, ranking, and conditional retrieval."""

    def __init__(
        self,
        service: RetrievalService,
        config: RetrievalConfig | None = None,
    ) -> None:
        self._service = service
        self._config = config if config is not None else RetrievalConfig()

    def retrieve(self, query: RetrievalQuery) -> EvidenceSet:
        """Return published evidence for a grounded turn, or an empty set.

        Implements: ADR-007 §Decision; INV-SCOPE-006, INV-CITE-001 (partial).
        """
        if not query.requires_grounding:
            return EvidenceSet()
        self._validate_query(query)

        try:
            candidates = tuple(self._service.search(query))
        except RetrievalUnavailableError:
            raise
        except Exception as exc:
            raise RetrievalUnavailableError("retrieval service failed") from exc

        published = [
            chunk
            for chunk in candidates
            if chunk.review_status == "published"
            and chunk.language == query.language
            and chunk.level == query.level
            and (query.topic is None or chunk.topic == query.topic)
            and chunk.score >= self._config.min_score
        ]
        withheld_ids = tuple(
            dict.fromkeys(
                chunk.chunk_id
                for chunk in candidates
                if chunk.review_status != "published"
            )
        )

        best_by_id: dict[str, RetrievedChunk] = {}
        for chunk in published:
            existing = best_by_id.get(chunk.chunk_id)
            if existing is None or chunk.score > existing.score:
                best_by_id[chunk.chunk_id] = chunk

        ordered: Sequence[RetrievedChunk] = sorted(
            best_by_id.values(),
            key=lambda chunk: (-chunk.score, chunk.chunk_id),
        )
        return EvidenceSet(
            chunks=tuple(ordered[: query.top_k]),
            withheld_ids=withheld_ids,
        )

    def _validate_query(self, query: RetrievalQuery) -> None:
        if not query.query.strip():
            raise InvalidRequestError("query must be non-empty")
        if query.language != LANGUAGE_ENGLISH:
            raise InvalidRequestError("language must be 'en'")
        if query.level not in CEFR_LEVELS:
            raise InvalidRequestError("level must be one of A1, A2, B1, B2")
        if not 1 <= query.top_k <= self._config.max_top_k:
            raise InvalidRequestError(
                f"top_k must be between 1 and {self._config.max_top_k}"
            )
