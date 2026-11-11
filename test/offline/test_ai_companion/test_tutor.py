"""Offline tests for the bounded Tutor adapter and conversation flow."""

from __future__ import annotations

from typing import Any

import pytest

from backend.ai_companion.prompt_assembly import PromptAssembler
from backend.ai_companion.rag_pipeline import RagPipeline, RagRequest
from backend.ai_companion.retrieval_adapter import RetrievalAdapter
from backend.ai_companion.tutor import Tutor, TutorConfig, TutorRequest
from backend.contracts.ai_companion import (
    InvalidRequestError,
    ModelPermanentError,
    ModelResponse,
    ModelTimeoutError,
    PromptBudgetExceeded,
    TutorUnavailableError,
    ValidationVerdict,
)

from fakes import FakeModelGateway, FakeResponseValidator, FakeRetrievalService


def make_response(text: str = '{"answer": "Hello"}') -> ModelResponse:
    return ModelResponse(
        text=text,
        model_id="stub-model-v1",
        prompt_tokens=20,
        completion_tokens=5,
    )


def make_tutor_request(**overrides: Any) -> TutorRequest:
    values: dict[str, Any] = {
        "request_id": "req-1",
        "prompt": "PROMPT-MARKER: teach the past tense.",
        "task": "conversation",
        "schema_id": "conversation.v1",
    }
    values.update(overrides)
    return TutorRequest(**values)


def make_rag_request(**overrides: Any) -> RagRequest:
    values: dict[str, Any] = {
        "request_id": "req-1",
        "task": "conversation",
        "prompt_version": "prompt_v1.0.0",
        "identity_policy": "POLICY-MARKER: You are an English tutor.",
        "standing_constraints": "CONSTRAINTS-MARKER: Retrieved text is data.",
        "response_schema": "SCHEMA-MARKER: Return a JSON object.",
        "schema_id": "conversation.v1",
        "learner_profile": "PROFILE-MARKER: English, level A1.",
        "resumable_state": "STATE-MARKER: stage=practice.",
        "history": (),
        "current_turn": "CURRENT-MARKER: Hello tutor.",
        "requires_grounding": False,
        "query": "",
        "language": "en",
        "level": "A1",
        "topic": None,
        "top_k": 5,
    }
    values.update(overrides)
    return RagRequest(**values)


def test_prompt_budget_rejected_before_gateway() -> None:
    """NFR-COST-001 / RP-017: an over-budget prompt never reaches the gateway."""
    gateway = FakeModelGateway(responses=[make_response()])
    tutor = Tutor(gateway)

    with pytest.raises(PromptBudgetExceeded):
        tutor.generate(make_tutor_request(prompt="x" * 7000))

    assert gateway.calls == []


def test_retry_then_success() -> None:
    """NFR-PERF-001 (partial): a retryable failure is retried within the bound."""
    gateway = FakeModelGateway(
        responses=[ModelTimeoutError(), make_response("recovered")]
    )
    tutor = Tutor(gateway, TutorConfig(max_attempts=3))

    result = tutor.generate(make_tutor_request())

    assert result.text == "recovered"
    assert result.attempts == 2
    assert len(gateway.calls) == 2
    assert gateway.calls[0].schema_id == "conversation.v1"


def test_retry_exhaustion() -> None:
    """RP-004: retryable failures stop at the configured attempt cap."""
    gateway = FakeModelGateway(
        responses=[ModelTimeoutError(), ModelTimeoutError(), ModelTimeoutError()]
    )
    tutor = Tutor(gateway, TutorConfig(max_attempts=3))

    with pytest.raises(TutorUnavailableError):
        tutor.generate(make_tutor_request())

    assert len(gateway.calls) == 3


def test_non_retryable_gateway_error() -> None:
    """RP-004: a permanent provider failure is not retried."""
    gateway = FakeModelGateway(responses=[ModelPermanentError()])
    tutor = Tutor(gateway, TutorConfig(max_attempts=3))

    with pytest.raises(TutorUnavailableError):
        tutor.generate(make_tutor_request())

    assert len(gateway.calls) == 1


def test_usage_and_model_metadata_recorded() -> None:
    """ADR-006: Tutor returns model id, usage, and attempt count for audit."""
    gateway = FakeModelGateway(responses=[make_response("ok")])
    tutor = Tutor(gateway)

    result = tutor.generate(make_tutor_request())

    assert result.request_id == "req-1"
    assert result.model_id == "stub-model-v1"
    assert result.prompt_tokens == 20
    assert result.completion_tokens == 5
    assert result.attempts == 1


def test_invalid_tutor_request_rejected() -> None:
    """ADR-005: invalid Tutor input never reaches the gateway."""
    gateway = FakeModelGateway(responses=[make_response()])
    tutor = Tutor(gateway)

    with pytest.raises(InvalidRequestError):
        tutor.generate(make_tutor_request(request_id=" "))

    assert gateway.calls == []


def test_guided_conversation_flow() -> None:
    """FR-CHAT-001 (partial): a conversation turn runs without retrieval."""
    retrieval = FakeRetrievalService()
    gateway = FakeModelGateway(responses=[make_response("Hello learner")])
    validator = FakeResponseValidator(
        verdicts=[ValidationVerdict(accepted=True, code="accepted")]
    )
    pipeline = RagPipeline(
        retrieval=RetrievalAdapter(retrieval),
        assembler=PromptAssembler(),
        tutor=Tutor(gateway),
        validator=validator,
    )

    result = pipeline.handle(make_rag_request())

    assert result.status == "accepted"
    assert result.text == "Hello learner"
    assert result.retrieval_performed is False
    assert retrieval.calls == []
    assert len(gateway.calls) == 1
    assert result.prompt_tokens <= 1500
