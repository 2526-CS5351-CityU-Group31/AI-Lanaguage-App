"""Offline tests for the published-only RetrievalAdapter."""

from __future__ import annotations

from typing import Any

import pytest

from backend.ai_companion.retrieval_adapter import RetrievalAdapter, RetrievalConfig
from backend.contracts.ai_companion import (
    InvalidRequestError,
    RetrievalQuery,
    RetrievalUnavailableError,
)

from fakes import FakeRetrievalService, make_chunk


def make_query(**overrides: Any) -> RetrievalQuery:
    values: dict[str, Any] = {
        "query": "When do I use the past tense?",
        "language": "en",
        "level": "A1",
        "topic": "grammar",
        "top_k": 5,
        "requires_grounding": True,
    }
    values.update(overrides)
    return RetrievalQuery(**values)


def test_published_only_filter_before_ranking() -> None:
    """ADR-007 / INV-CITE-001 (partial): unpublished chunks never reach the caller."""
    service = FakeRetrievalService(
        chunks=(
            make_chunk("draft-1", score=0.99, review_status="draft"),
            make_chunk("retired-1", score=0.95, review_status="retired"),
            make_chunk("published-1", score=0.40),
        )
    )
    adapter = RetrievalAdapter(service)

    result = adapter.retrieve(make_query(top_k=10))

    assert [chunk.chunk_id for chunk in result.chunks] == ["published-1"]
    assert result.published_ids == ("published-1",)


def test_language_level_topic_prefilter() -> None:
    """ADR-007: language, CEFR level, and topic are filtered before ranking."""
    service = FakeRetrievalService(
        chunks=(
            make_chunk("wrong-language", language="fr", score=0.99),
            make_chunk("wrong-level", level="B2", score=0.98),
            make_chunk("wrong-topic", topic="vocabulary", score=0.97),
            make_chunk("match", score=0.50),
        )
    )
    adapter = RetrievalAdapter(service)

    result = adapter.retrieve(make_query(level="A1", topic="grammar", top_k=10))

    assert [chunk.chunk_id for chunk in result.chunks] == ["match"]


def test_top_k_score_threshold_and_dedupe() -> None:
    """ADR-007: dedupe by chunk_id, keep highest score, threshold, then top_k."""
    service = FakeRetrievalService(
        chunks=(
            make_chunk("c1", text="lower duplicate", score=0.80),
            make_chunk("c2", score=0.70),
            make_chunk("c1", text="higher duplicate", score=0.95),
            make_chunk("c3", score=0.10),
        )
    )
    adapter = RetrievalAdapter(service, RetrievalConfig(min_score=0.35))

    result = adapter.retrieve(make_query(top_k=2))

    assert [chunk.chunk_id for chunk in result.chunks] == ["c1", "c2"]
    assert result.chunks[0].text == "higher duplicate"
    assert "c3" not in result.published_ids


def test_empty_candidates_return_empty_evidence() -> None:
    """ADR-007: an empty retrieval result is a valid EvidenceSet, not an exception."""
    adapter = RetrievalAdapter(FakeRetrievalService())

    result = adapter.retrieve(make_query())

    assert result.is_empty is True
    assert result.published_ids == ()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"query": "   "}, "query"),
        ({"language": "fr"}, "language"),
        ({"level": "C1"}, "level"),
        ({"top_k": 0}, "top_k"),
        ({"top_k": 11}, "top_k"),
    ],
)
def test_invalid_retrieval_query_rejected(overrides: dict[str, Any], message: str) -> None:
    """ADR-007: invalid retrieval inputs are rejected before the service call."""
    service = FakeRetrievalService()
    adapter = RetrievalAdapter(service)

    with pytest.raises(InvalidRequestError, match=message):
        adapter.retrieve(make_query(**overrides))

    assert service.calls == []


def test_retrieval_unavailable_returns_typed_error() -> None:
    """RP-006: retrieval failure is typed so the pipeline can abstain safely."""
    service = FakeRetrievalService(error=RetrievalUnavailableError("offline"))
    adapter = RetrievalAdapter(service)

    with pytest.raises(RetrievalUnavailableError):
        adapter.retrieve(make_query())

    assert len(service.calls) == 1


def test_service_exception_is_wrapped_as_retrieval_unavailable() -> None:
    """RP-006: unexpected retrieval failures fail closed rather than escaping raw."""
    service = FakeRetrievalService(error=RuntimeError("boom"))
    adapter = RetrievalAdapter(service)

    with pytest.raises(RetrievalUnavailableError):
        adapter.retrieve(make_query())
