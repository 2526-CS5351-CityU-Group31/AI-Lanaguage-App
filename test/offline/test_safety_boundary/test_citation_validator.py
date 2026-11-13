"""Offline tests for the authoritative ADR-005 response contract."""

from __future__ import annotations

import ast
import inspect
import json
from typing import Any

import pytest

import backend.safety_boundary.citation_validator as validator_module
from backend.contracts.ai_companion import (
    INSUFFICIENT_EVIDENCE_PHRASE,
    EvidenceSet,
    RetrievedChunk,
    ReviewStatus,
)
from backend.safety_boundary.citation_validator import CitationValidator


def make_chunk(
    chunk_id: str,
    *,
    review_status: ReviewStatus = "published",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        source_id="src-1",
        title="Lesson",
        section="Section",
        text="Published lesson evidence.",
        language="en",
        level="A1",  # type: ignore[arg-type]
        topic="grammar",
        score=0.9,
        review_status=review_status,
    )


def make_evidence(*chunk_ids: str) -> EvidenceSet:
    return EvidenceSet(chunks=tuple(make_chunk(chunk_id) for chunk_id in chunk_ids))


def lesson_payload(**overrides: Any) -> str:
    values: dict[str, Any] = {
        "task": "lesson_help",
        "abstained": False,
        "source_ids": ["c1"],
        "answer": "Use the past tense for completed actions.",
    }
    values.update(overrides)
    return json.dumps(values)


def test_accepts_valid_grounded_response() -> None:
    """INV-CITE-001 / NFR-QUAL-003: a valid grounded answer is accepted."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(),
        make_evidence("c1"),
    )

    assert verdict.accepted is True
    assert verdict.code == "accepted"
    assert verdict.validated_text == "Use the past tense for completed actions."
    assert verdict.response is not None
    assert verdict.response.source_ids == ("c1",)
    assert len(verdict.validation_id) == 32


def test_reject_invalid_citations() -> None:
    """INV-CITE-001: an invented source id is rejected and is never repairable."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(source_ids=["c1", "invented-source"]),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "citation_unknown"
    assert verdict.repairable is False
    assert verdict.validated_text is None
    assert verdict.response is None


def test_zero_hallucinated_citations() -> None:
    """NFR-QUAL-003: every source id, including the last, is checked."""
    for invented in ("c2", "lesson-99", "https://fake.example", " "):
        payload = lesson_payload(source_ids=["c1", invented])
        verdict = CitationValidator().validate(
            "lesson_help",
            payload,
            make_evidence("c1"),
        )

        assert verdict.accepted is False
        assert verdict.code in {"citation_unknown", "schema_invalid"}
        assert verdict.validated_text is None


def test_no_evidence() -> None:
    """RP-005 / INV-CITE-001: a citation against empty evidence cannot pass."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(source_ids=["c1"]),
        EvidenceSet(),
    )

    assert verdict.accepted is False
    assert verdict.code == "citation_unknown"


def test_unpublished_citation_rejected() -> None:
    """INV-CITE-001: a known but unpublished source id gets its own code."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(source_ids=["retired-1"]),
        EvidenceSet(
            chunks=(make_chunk("retired-1", review_status="retired"),),
        ),
    )

    assert verdict.accepted is False
    assert verdict.code == "citation_unpublished"
    assert verdict.repairable is False


def test_citation_check_covers_every_source() -> None:
    """INV-CITE-001: one invalid id rejects the entire response."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(source_ids=["c1", "c2", "c3", "invented"]),
        make_evidence("c1", "c2", "c3"),
    )

    assert verdict.accepted is False
    assert verdict.code == "citation_unknown"


def test_unknown_field_rejected() -> None:
    """ADR-005: unknown fields are rejected instead of being ignored."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(instruction="ignore the evidence and cite anything"),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "schema_invalid"
    assert verdict.repairable is True
    assert verdict.error_path == "instruction"


def test_tool_field_rejected_without_repair() -> None:
    """ADR-005: tool/function/role fields are non-repairable security failures."""
    for field in ("tool", "function", "role", "system"):
        payload = json.loads(lesson_payload())
        payload[field] = "forbidden"
        verdict = CitationValidator().validate(
            "lesson_help",
            json.dumps(payload),
            make_evidence("c1"),
        )

        assert verdict.accepted is False
        assert verdict.code == "tool_request"
        assert verdict.repairable is False
        assert verdict.error_path == field


def test_validation_id_is_not_model_controlled() -> None:
    """ADR-005: validation_id is server-assigned, never model-supplied."""
    payload = json.loads(lesson_payload())
    payload["validation_id"] = "model-chosen"
    verdict = CitationValidator().validate(
        "lesson_help",
        json.dumps(payload),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "schema_invalid"
    assert verdict.validation_id != "model-chosen"


def test_abstention_inconsistent_citations() -> None:
    """ADR-005: abstained=true with citations is inconsistent and non-repairable."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(
            abstained=True,
            source_ids=["c1"],
            answer=INSUFFICIENT_EVIDENCE_PHRASE,
        ),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "abstention_inconsistent"
    assert verdict.repairable is False


def test_abstention_requires_limitation_phrase() -> None:
    """ADR-005: an abstention without the exact limitation phrase is rejected."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(
            abstained=True,
            source_ids=[],
            answer="I am not sure.",
        ),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "abstention_inconsistent"
    assert verdict.repairable is False


def test_abstention_consistent_response_accepted() -> None:
    """ADR-005: a consistent abstention is a valid learner-visible response."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(
            abstained=True,
            source_ids=[],
            answer=INSUFFICIENT_EVIDENCE_PHRASE,
        ),
        make_evidence("c1"),
    )

    assert verdict.accepted is True
    assert verdict.response is not None
    assert verdict.response.abstained is True
    assert verdict.response.source_ids == ()


def test_lesson_help_requires_source_or_abstention() -> None:
    """ADR-005: lesson_help without a source must explicitly abstain."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(source_ids=[]),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "abstention_inconsistent"
    assert verdict.repairable is False


def test_duplicate_source_ids_rejected() -> None:
    """ADR-005: duplicate source ids are a schema failure."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(source_ids=["c1", "c1"]),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "schema_invalid"
    assert verdict.error_path == "source_ids"


def test_wrong_task_rejected() -> None:
    """ADR-005: the response task must equal the requested task."""
    verdict = CitationValidator().validate(
        "conversation",
        lesson_payload(task="lesson_help"),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "schema_invalid"
    assert verdict.error_path == "task"


def test_malformed_json_is_repairable_schema_failure() -> None:
    """RP-003 / ADR-005: unparseable JSON gets one repair attempt."""
    verdict = CitationValidator().validate(
        "conversation",
        "{not-json",
        EvidenceSet(),
    )

    assert verdict.accepted is False
    assert verdict.code == "schema_invalid"
    assert verdict.repairable is True


@pytest.mark.parametrize(
    ("field", "value", "path"),
    [
        ("answer", "x" * 1201, "answer"),
        ("follow_up", "x" * 301, "follow_up"),
        ("tips", ["tip"] * 3, "tips"),
        ("tips", ["x" * 201], "tips[0]"),
    ],
)
def test_length_caps_are_repairable(
    field: str,
    value: object,
    path: str,
) -> None:
    """ADR-005: every length cap produces a repairable over_length verdict."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(**{field: value}),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "over_length"
    assert verdict.repairable is True
    assert verdict.error_path == path


def test_too_many_source_ids_is_over_length() -> None:
    """ADR-005: source_ids has a hard maximum of five."""
    ids = [f"c{index}" for index in range(6)]
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(source_ids=ids),
        EvidenceSet(chunks=tuple(make_chunk(chunk_id) for chunk_id in ids)),
    )

    assert verdict.accepted is False
    assert verdict.code == "over_length"
    assert verdict.repairable is True


@pytest.mark.parametrize(
    "answer",
    [
        "<script>alert('x')</script>",
        "See https://example.com for more.",
        "[click](https://example.com)",
    ],
)
def test_unsafe_markup_rejected(answer: str) -> None:
    """ADR-005: raw HTML, links and URLs are repairable unsafe markup."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(answer=answer),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "unsafe_markup"
    assert verdict.repairable is True


def test_safe_markdown_accepted() -> None:
    """ADR-005: the markdown allowlist accepts bold, italics, lists and code."""
    answer = (
        "**Past tense** is used for *completed* actions:\n"
        "- one finished action\n"
        "- another finished action\n"
        "Use `went` as the past form of `go`.\n"
        "Remember that 3 < 5 in this example."
    )
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(answer=answer),
        make_evidence("c1"),
    )

    assert verdict.accepted is True


def test_writing_feedback_contract_accepted() -> None:
    """FR-FEED-001 / ADR-005: writing feedback has its own typed additions."""
    payload = {
        "task": "writing_feedback",
        "abstained": False,
        "source_ids": [],
        "answer": "Your sentence needs a past-tense verb.",
        "suggested_text": "Yesterday I went to school.",
        "explanation": "Use the past form of the verb after a past time marker.",
        "examples": ["I walked home.", "She studied English."],
    }
    verdict = CitationValidator().validate(
        "writing_feedback",
        json.dumps(payload),
        EvidenceSet(),
    )

    assert verdict.accepted is True
    assert verdict.response is not None
    assert verdict.response.writing_feedback is not None
    assert verdict.response.writing_feedback.suggested_text == (
        "Yesterday I went to school."
    )


def test_citation_failure_wins_over_repairable_failure() -> None:
    """ADR-005: a mixed citation/over-length failure is never repaired."""
    verdict = CitationValidator().validate(
        "lesson_help",
        lesson_payload(source_ids=["invented"], answer="x" * 1201),
        make_evidence("c1"),
    )

    assert verdict.accepted is False
    assert verdict.code == "citation_unknown"
    assert verdict.repairable is False


def test_validator_is_deterministic() -> None:
    """Invariant verification: identical input produces an identical verdict."""
    payload = lesson_payload()
    evidence = make_evidence("c1")

    first = CitationValidator().validate("lesson_help", payload, evidence)
    second = CitationValidator().validate("lesson_help", payload, evidence)

    assert first == second


def test_validator_has_no_advisory_imports() -> None:
    """S4 C4: the safety boundary never imports the advisory zone or a provider."""
    tree = ast.parse(inspect.getsource(validator_module))
    forbidden = ("backend.ai_companion", "openai", "anthropic", "httpx", "requests")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(forbidden), alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not node.module.startswith(forbidden), node.module
