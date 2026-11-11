"""Deterministic offline fakes for AI companion tests.

These fakes record calls and return queued results. They perform no network,
database, filesystem, or provider access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from backend.contracts.ai_companion import (
    EvidenceSet,
    ModelRequest,
    ModelResponse,
    RetrievedChunk,
    RetrievalQuery,
    ReviewStatus,
    TaskType,
    ValidationVerdict,
)


def make_chunk(
    chunk_id: str,
    *,
    source_id: str = "src-1",
    title: str = "Lesson",
    section: str = "Section",
    text: str = "Lesson evidence.",
    language: str = "en",
    level: str = "A1",
    topic: str | None = "grammar",
    score: float = 0.9,
    review_status: ReviewStatus = "published",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        title=title,
        section=section,
        text=text,
        language=language,
        level=level,  # type: ignore[arg-type]
        topic=topic,
        score=score,
        review_status=review_status,
    )


@dataclass
class FakeRetrievalService:
    """RetrievalService stub with call recording and queued failure injection."""

    chunks: Sequence[RetrievedChunk] = ()
    error: Exception | None = None
    calls: list[RetrievalQuery] = field(default_factory=list)

    def search(self, query: RetrievalQuery) -> Sequence[RetrievedChunk]:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return self.chunks


@dataclass
class FakeModelGateway:
    """ModelGateway stub returning queued responses or raising queued errors."""

    responses: list[ModelResponse | Exception] = field(default_factory=list)
    calls: list[ModelRequest] = field(default_factory=list)

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("FakeModelGateway received an unexpected call")
        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


@dataclass
class FakeResponseValidator:
    """ResponseValidator stub returning queued verdicts or raising queued errors."""

    verdicts: list[ValidationVerdict | Exception] = field(default_factory=list)
    calls: list[tuple[TaskType, str, EvidenceSet]] = field(default_factory=list)

    def validate(
        self,
        task: TaskType,
        raw_output: str,
        evidence: EvidenceSet,
    ) -> ValidationVerdict:
        self.calls.append((task, raw_output, evidence))
        if not self.verdicts:
            raise AssertionError("FakeResponseValidator received an unexpected call")
        next_item = self.verdicts.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item
