"""Offline tests for INV-SCOPE-006 conditional retrieval routing."""

from __future__ import annotations

from typing import Any

from backend.ai_companion.retrieval_adapter import RetrievalAdapter
from backend.contracts.ai_companion import RetrievalQuery

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


def test_conditional_retrieval_routing() -> None:
    """INV-SCOPE-006: retrieval runs only when requires_grounding is true."""
    service = FakeRetrievalService(chunks=(make_chunk("c1"),))
    adapter = RetrievalAdapter(service)

    ungrounded = adapter.retrieve(make_query(requires_grounding=False))
    assert ungrounded.is_empty is True
    assert service.calls == []

    grounded = adapter.retrieve(make_query(requires_grounding=True))
    assert [chunk.chunk_id for chunk in grounded.chunks] == ["c1"]
    assert len(service.calls) == 1


def test_ungrounded_retrieval_returns_empty_even_with_candidates() -> None:
    """INV-SCOPE-006: ungrounded turns never observe retrieval candidates."""
    service = FakeRetrievalService(chunks=(make_chunk("c1"), make_chunk("c2")))
    adapter = RetrievalAdapter(service)

    result = adapter.retrieve(make_query(requires_grounding=False))

    assert result.is_empty is True
    assert result.published_ids == ()
    assert service.calls == []
