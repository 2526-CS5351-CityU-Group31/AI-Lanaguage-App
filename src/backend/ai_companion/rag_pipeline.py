"""RagPipeline - proposal-only AI orchestration with an injected validator port.

Element: RagPipeline
Implements: ADR-001 §Decision; ADR-005 §Decision; ADR-006 §Assembly pipeline;
ADR-007 §Decision; FR-RAG-001, INV-SCOPE-006, INV-CITE-001 (partial).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.ai_companion.prompt_assembly import (
    EvidenceChunk,
    HistoryTurn,
    PromptAssembler,
    PromptAssemblyRequest,
)
from backend.ai_companion.retrieval_adapter import RetrievalAdapter
from backend.ai_companion.tutor import Tutor, TutorRequest, TutorResult
from backend.contracts.ai_companion import (
    CEFR_LEVELS,
    LANGUAGE_ENGLISH,
    CefrLevel,
    EvidenceSet,
    InvalidRequestError,
    ResponseValidator,
    RetrievalQuery,
    RetrievalUnavailableError,
    TaskType,
    TutorUnavailableError,
    ValidationVerdict,
)

RagResultStatus = Literal["accepted", "rejected", "abstained"]


@dataclass(frozen=True)
class RagRequest:
    """FR-RAG-001 / FR-CHAT-001: one caller-supplied AI turn."""

    request_id: str
    task: TaskType
    prompt_version: str
    identity_policy: str
    standing_constraints: str
    response_schema: str
    schema_id: str
    learner_profile: str
    resumable_state: str
    history: tuple[HistoryTurn, ...]
    current_turn: str
    requires_grounding: bool
    query: str
    language: str
    level: CefrLevel
    topic: str | None
    top_k: int


@dataclass(frozen=True)
class RagResult:
    """ADR-005: outcome of a proposal-only turn; no unvalidated text is returned."""

    request_id: str
    status: RagResultStatus
    text: str | None
    evidence_ids: tuple[str, ...]
    prompt_tokens: int
    retrieval_performed: bool
    validation: ValidationVerdict | None
    tutor: TutorResult | None
    reason: str | None = None


class RagPipeline:
    """ADR-001: advisory orchestration; it never writes and never validates citations."""

    def __init__(
        self,
        retrieval: RetrievalAdapter,
        assembler: PromptAssembler,
        tutor: Tutor,
        validator: ResponseValidator,
    ) -> None:
        self._retrieval = retrieval
        self._assembler = assembler
        self._tutor = tutor
        self._validator = validator

    def handle(self, request: RagRequest) -> RagResult:
        """Route, retrieve conditionally, assemble, call Tutor, and validate.

        Implements: ADR-005 §Decision; ADR-007 §Decision; FR-RAG-001.
        """
        self._validate_request(request)

        evidence = EvidenceSet()
        retrieval_performed = False
        if request.requires_grounding:
            retrieval_performed = True
            try:
                evidence = self._retrieval.retrieve(
                    RetrievalQuery(
                        query=request.query,
                        language=request.language,
                        level=self._level(request.level),
                        topic=request.topic,
                        top_k=request.top_k,
                        requires_grounding=True,
                    )
                )
            except RetrievalUnavailableError:
                return self._abstained(
                    request=request,
                    reason="retrieval_unavailable",
                    retrieval_performed=True,
                )

            if evidence.is_empty:
                return self._abstained(
                    request=request,
                    reason="no_evidence",
                    retrieval_performed=True,
                )

        prompt_evidence = tuple(
            EvidenceChunk(
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                section=chunk.section,
                text=chunk.text,
            )
            for chunk in evidence.chunks
        )
        assembly = self._assembler.assemble(
            PromptAssemblyRequest(
                prompt_version=request.prompt_version,
                identity_policy=request.identity_policy,
                standing_constraints=request.standing_constraints,
                response_schema=request.response_schema,
                learner_profile=request.learner_profile,
                resumable_state=request.resumable_state,
                evidence=prompt_evidence,
                history=request.history,
                current_turn=request.current_turn,
            )
        )

        try:
            tutor_result = self._tutor.generate(
                TutorRequest(
                    request_id=request.request_id,
                    prompt=assembly.prompt,
                    task=request.task,
                    schema_id=request.schema_id,
                )
            )
        except TutorUnavailableError:
            return self._abstained(
                request=request,
                reason="tutor_unavailable",
                retrieval_performed=retrieval_performed,
                evidence=evidence,
                prompt_tokens=assembly.token_count,
            )

        try:
            verdict = self._validator.validate(
                request.task,
                tutor_result.text,
                evidence,
            )
        except Exception:
            return RagResult(
                request_id=request.request_id,
                status="rejected",
                text=None,
                evidence_ids=evidence.published_ids,
                prompt_tokens=assembly.token_count,
                retrieval_performed=retrieval_performed,
                validation=None,
                tutor=tutor_result,
                reason="validator_error",
            )

        if not verdict.accepted:
            return RagResult(
                request_id=request.request_id,
                status="rejected",
                text=None,
                evidence_ids=evidence.published_ids,
                prompt_tokens=assembly.token_count,
                retrieval_performed=retrieval_performed,
                validation=verdict,
                tutor=tutor_result,
                reason=verdict.code,
            )

        return RagResult(
            request_id=request.request_id,
            status="accepted",
            text=(
                verdict.validated_text
                if verdict.validated_text is not None
                else tutor_result.text
            ),
            evidence_ids=evidence.published_ids,
            prompt_tokens=assembly.token_count,
            retrieval_performed=retrieval_performed,
            validation=verdict,
            tutor=tutor_result,
        )

    def _abstained(
        self,
        *,
        request: RagRequest,
        reason: str,
        retrieval_performed: bool,
        evidence: EvidenceSet | None = None,
        prompt_tokens: int = 0,
    ) -> RagResult:
        return RagResult(
            request_id=request.request_id,
            status="abstained",
            text=None,
            evidence_ids=evidence.published_ids if evidence is not None else (),
            prompt_tokens=prompt_tokens,
            retrieval_performed=retrieval_performed,
            validation=None,
            tutor=None,
            reason=reason,
        )

    def _validate_request(self, request: RagRequest) -> None:
        required = (
            request.request_id,
            request.prompt_version,
            request.identity_policy,
            request.standing_constraints,
            request.response_schema,
            request.schema_id,
            request.current_turn,
        )
        if any(not value.strip() for value in required):
            raise InvalidRequestError("required RagRequest text fields must be non-empty")
        if request.task not in ("conversation", "lesson_help"):
            raise InvalidRequestError("task must be conversation or lesson_help")
        if request.task == "lesson_help" and not request.requires_grounding:
            raise InvalidRequestError("lesson_help requires grounding")
        if request.language != LANGUAGE_ENGLISH:
            raise InvalidRequestError("language must be 'en'")
        self._level(request.level)
        if request.requires_grounding and not request.query.strip():
            raise InvalidRequestError("grounded requests require a query")

    def _level(self, level: str) -> CefrLevel:
        if level not in CEFR_LEVELS:
            raise InvalidRequestError("level must be one of A1, A2, B1, B2")
        return level
