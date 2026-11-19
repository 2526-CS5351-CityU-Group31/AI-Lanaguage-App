"""Offline tests for the live chat request builder.

Implements: FR-RAG-001; ADR-005 (task-specific response contracts).
"""

from __future__ import annotations

from backend.api.pipeline_factory import _build_rag_request


def test_lesson_help_uses_its_own_schema() -> None:
    """FR-RAG-001: lesson_help must not be prompted with a conversation schema."""
    request = _build_rag_request(
        request_id="req-lesson-schema",
        task="lesson_help",
        message="Explain the difference between 'a' and 'an'.",
        requires_grounding=True,
        topic=None,
        level="A2",
    )

    assert '"task": "lesson_help"' in request.response_schema
    assert "chunk_id from evidence" in request.response_schema
    assert '"task": "conversation"' not in request.response_schema


def test_conversation_keeps_the_conversation_schema() -> None:
    """FR-RAG-001: conversation turns keep the conversation response contract."""
    request = _build_rag_request(
        request_id="req-conversation-schema",
        task="conversation",
        message="Hello, how are you?",
        requires_grounding=False,
        topic=None,
        level="A2",
    )

    assert '"task": "conversation"' in request.response_schema
    assert '"task": "lesson_help"' not in request.response_schema
