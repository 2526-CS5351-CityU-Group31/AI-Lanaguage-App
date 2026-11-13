"""AI companion contracts - typed DTOs, ports, and typed errors.

Element: support contracts for the AI companion foundation
Implements: ADR-001 advisory boundary; ADR-005 validator port; ADR-006/ADR-007
integration seams. This module contains no authority decision and no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

CefrLevel = Literal["A1", "A2", "B1", "B2"]
TaskType = Literal["conversation", "lesson_help", "writing_feedback"]
ReviewStatus = Literal["published", "draft", "retired"]

LANGUAGE_ENGLISH = "en"
CEFR_LEVELS: tuple[CefrLevel, ...] = ("A1", "A2", "B1", "B2")
DEFAULT_TOP_K = 5
MAX_TOP_K = 10
DEFAULT_MIN_SCORE = 0.35

# ADR-005 response-contract caps. These are shared by the prompt catalogue and
# the authoritative validator so the model instruction and the gate cannot drift.
MAX_SOURCE_IDS = 5
MAX_ANSWER_CHARS = 1200
MAX_FOLLOW_UP_CHARS = 300
MAX_TIPS = 2
MAX_TIP_CHARS = 200
MAX_SUGGESTED_TEXT_CHARS = 1500
MAX_EXPLANATION_CHARS = 800
MAX_EXAMPLES = 2
MAX_EXAMPLE_CHARS = 300
MAX_RAW_OUTPUT_CHARS = 12000

# ADR-005 / INV-CITE-001: deterministic learner-visible fallback strings.
INSUFFICIENT_EVIDENCE_PHRASE = (
    "I don't have enough published lesson evidence to answer that."
)
SAFE_FALLBACK_MESSAGE = (
    "I couldn't produce a verified answer just now. Please try again."
)


@dataclass(frozen=True)
class RetrievedChunk:
    """ADR-007: one candidate chunk returned by the retrieval seam."""

    chunk_id: str
    source_id: str
    title: str
    section: str
    text: str
    language: str
    level: CefrLevel
    topic: str | None
    score: float
    review_status: ReviewStatus


@dataclass(frozen=True)
class EvidenceSet:
    """ADR-007 / INV-CITE-001: the adapter-approved, published evidence set.

    ``withheld_ids`` carries only identifiers of candidates the adapter refused
    to serve because they were not published. No withheld text enters a prompt.
    """

    chunks: tuple[RetrievedChunk, ...] = ()
    withheld_ids: tuple[str, ...] = ()

    @property
    def published_ids(self) -> tuple[str, ...]:
        """INV-CITE-001: IDs available for authoritative citation validation."""
        return tuple(
            chunk.chunk_id
            for chunk in self.chunks
            if chunk.review_status == "published"
        )

    @property
    def unpublished_ids(self) -> tuple[str, ...]:
        """INV-CITE-001: known IDs that exist but must never be cited."""
        candidates = [
            *self.withheld_ids,
            *(chunk.chunk_id for chunk in self.chunks if chunk.review_status != "published"),
        ]
        return tuple(dict.fromkeys(candidates))

    @property
    def is_empty(self) -> bool:
        return not self.chunks


@dataclass(frozen=True)
class WritingFeedback:
    """ADR-005 §Task-specific additions: proposal-only writing feedback."""

    suggested_text: str
    explanation: str
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidatedResponse:
    """ADR-005: the typed response the validator has accepted.

    Only this object may produce learner-visible text. Source titles and
    sections are resolved later from server-held evidence, never from model text.
    """

    task: TaskType
    abstained: bool
    source_ids: tuple[str, ...]
    answer: str
    follow_up: str | None = None
    tips: tuple[str, ...] = ()
    writing_feedback: WritingFeedback | None = None


@dataclass(frozen=True)
class RetrievalQuery:
    """INV-SCOPE-006: a retrieval request; the adapter gates on requires_grounding."""

    query: str
    language: str
    level: CefrLevel
    topic: str | None
    top_k: int
    requires_grounding: bool


class RetrievalService(Protocol):
    """ADR-007: read-only retrieval port; concrete DB implementation is out of scope."""

    def search(self, query: RetrievalQuery) -> Sequence[RetrievedChunk]:
        """Return candidate chunks; the adapter applies publication and ranking rules."""
        ...


@dataclass(frozen=True)
class ModelRequest:
    """ADR-005 / ADR-006: one structured-output request to the model gateway."""

    request_id: str
    prompt: str
    task: TaskType
    schema_id: str
    timeout_ms: int
    max_output_tokens: int
    temperature: float = 0.0


@dataclass(frozen=True)
class ModelResponse:
    """ADR-006: provider response plus usage metadata."""

    text: str
    model_id: str
    prompt_tokens: int
    completion_tokens: int


class ModelGateway(Protocol):
    """ADR-001: the only model-provider seam; concrete provider client is out of scope."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Return one model response or raise a typed gateway error."""
        ...


@dataclass(frozen=True)
class ValidationVerdict:
    """ADR-005: authoritative validator result consumed by RagPipeline."""

    accepted: bool
    code: str
    repairable: bool = False
    error_path: str = ""
    validated_text: str | None = None
    response: ValidatedResponse | None = None
    validation_id: str = ""
    detail: str = ""


class ResponseValidator(Protocol):
    """ADR-005 / INV-CITE-001: authoritative gate injected from the safety lane."""

    def validate(
        self,
        task: TaskType,
        raw_output: str,
        evidence: EvidenceSet,
    ) -> ValidationVerdict:
        """Return a deterministic verdict; RagPipeline never overrides a rejection."""
        ...


class AiCompanionError(Exception):
    """Base class for typed AI companion failures."""


class InvalidRequestError(AiCompanionError, ValueError):
    """ADR-005/ADR-007: invalid caller input that must not reach an external call."""


class RetrievalUnavailableError(AiCompanionError):
    """RP-006: retrieval failed; the pipeline abstains instead of fabricating evidence."""


class PromptBudgetExceeded(AiCompanionError):
    """NFR-COST-001 / RP-017: prompt exceeds the configured token budget."""


class ModelGatewayError(AiCompanionError):
    """RP-004/RP-009: typed gateway failure with a retryability decision."""

    retryable: bool

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ModelTimeoutError(ModelGatewayError):
    """RP-004: provider timeout; retryable within the Tutor bound."""

    def __init__(self, message: str = "model gateway timed out") -> None:
        super().__init__(message, retryable=True)


class ModelRateLimitError(ModelGatewayError):
    """RP-009: provider rate limit; retryable within the Tutor bound."""

    def __init__(self, message: str = "model gateway rate limited") -> None:
        super().__init__(message, retryable=True)


class ModelPermanentError(ModelGatewayError):
    """RP-004: non-retryable provider failure."""

    def __init__(self, message: str = "model gateway failed permanently") -> None:
        super().__init__(message, retryable=False)


class TutorUnavailableError(AiCompanionError):
    """RP-004: Tutor exhausted its bounded attempts or received a permanent failure."""
