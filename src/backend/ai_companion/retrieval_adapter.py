"""RetrievalAdapter - conditional, published-only retrieval over an injected port.

Element: RetrievalAdapter
Implements: ADR-007 §Decision/§Ingestion flow step 4; INV-SCOPE-006;
FR-RAG-001 (deterministic lexical ranking over the candidate window).

Ranking is lexical overlap over the candidates returned by the RetrievalService,
with the provider score as the tie-breaker. A larger corpus needs ranking in SQL
or an embedding adapter (NFR-QUAL-001); this keeps the current 18-chunk corpus
deterministic without a provider call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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


_TERM_PATTERN = re.compile(r"[a-z0-9']+")
_STOPWORDS = frozenset(
    {
        "a", "about", "am", "an", "and", "are", "as", "at", "be", "been",
        "being", "between", "but", "by", "can", "correct", "correction",
        "could", "definition", "did", "difference", "do", "does", "english",
        "example", "examples", "explain", "for", "from", "grammar", "had",
        "has", "have", "he", "her", "him", "his", "how", "i", "if", "in",
        "is", "it", "its", "language", "learn", "learning", "lesson", "mean",
        "meaning", "me", "my", "no", "not", "of", "on", "or", "our",
        "practice", "practise", "please", "rule", "she", "should", "so",
        "tell", "than", "that", "the", "their", "them", "then", "there",
        "these", "they", "this", "those", "to", "usage", "us", "was", "we",
        "were", "what", "when", "where", "which", "who", "why", "will",
        "with", "would", "yes", "you", "your",
    }
)


def _query_terms(query: str) -> frozenset[str]:
    """Return the content terms of a query (FR-RAG-001)."""
    return frozenset(
        term
        for term in _TERM_PATTERN.findall(query.lower())
        if term not in _STOPWORDS
    )


def _lexical_score(query_terms: frozenset[str], chunk: RetrievedChunk) -> float:
    """Return a weighted lexical overlap score (FR-RAG-001).

    A title match is stronger evidence than a body match: "Present Simple"
    must outrank a past-simple chunk that merely mentions "present perfect".
    """
    if not query_terms:
        return 0.0
    title_terms = set(_TERM_PATTERN.findall(chunk.title.lower()))
    all_terms = set(
        _TERM_PATTERN.findall(
            f"{chunk.title} {chunk.section} {chunk.text}".lower()
        )
    )
    title_score = len(query_terms & title_terms) / len(query_terms)
    text_score = len(query_terms & all_terms) / len(query_terms)
    return 3.0 * title_score + text_score


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

        query_terms = _query_terms(query.query)
        best_by_id: dict[str, tuple[RetrievedChunk, float]] = {}
        for chunk in published:
            lexical = _lexical_score(query_terms, chunk)
            existing = best_by_id.get(chunk.chunk_id)
            if existing is None or (chunk.score, lexical) > (
                existing[0].score,
                existing[1],
            ):
                best_by_id[chunk.chunk_id] = (chunk, lexical)

        ordered = sorted(
            best_by_id.values(),
            key=lambda item: (-item[1], -item[0].score, item[0].chunk_id),
        )
        return EvidenceSet(
            chunks=tuple(chunk for chunk, _ in ordered[: query.top_k]),
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
