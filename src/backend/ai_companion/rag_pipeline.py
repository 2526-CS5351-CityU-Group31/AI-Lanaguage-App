"""RagPipeline - proposal-only AI orchestration with an injected validator port.

Element: RagPipeline
Implements: ADR-001 §Decision; ADR-005 §Decision and §Responsibility map;
ADR-006 §Assembly pipeline; ADR-007 §Decision; FR-RAG-001, INV-SCOPE-006,
INV-CITE-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from backend.ai_companion.prompt_assembly import (
    EvidenceChunk,
    HistoryTurn,
    PromptAssembler,
    PromptAssemblyRequest,
    PromptCatalog,
    PromptCatalogError,
    PromptSchema,
    estimate_tokens,
    load_prompt_catalog,
)
from backend.ai_companion.retrieval_adapter import RetrievalAdapter
from backend.ai_companion.tutor import Tutor, TutorRequest, TutorResult
from backend.contracts.ai_companion import (
    CEFR_LEVELS,
    INSUFFICIENT_EVIDENCE_PHRASE,
    LANGUAGE_ENGLISH,
    SAFE_FALLBACK_MESSAGE,
    CefrLevel,
    EvidenceSet,
    InvalidRequestError,
    ResponseValidator,
    RetrievalQuery,
    RetrievalUnavailableError,
    TaskType,
    TutorUnavailableError,
    ValidatedResponse,
    ValidationVerdict,
)

RagResultStatus = Literal["accepted", "rejected", "abstained"]

# ADR-005 §Decision: only these failures may consume the single repair attempt.
# The pipeline keeps its own allowlist so a validator bug cannot turn a citation
# or authority failure into a retry.
SAFE_REPAIR_CODES: frozenset[str] = frozenset(
    ("schema_invalid", "over_length", "unsafe_markup")
)
ABSTENTION_CODES: frozenset[str] = frozenset(
    ("citation_unknown", "citation_unpublished", "abstention_inconsistent")
)
DEFAULT_REPAIR_TEMPLATE = (
    "Your previous response was rejected with code {code} at {error_path}: "
    "{detail}. Return only a corrected JSON object matching the task schema. "
    "Do not add, remove or change any source_ids."
)
DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@dataclass(frozen=True)
class RagRequest:
    """FR-RAG-001 / FR-CHAT-001: one caller-supplied AI turn.

    ``identity_policy``, ``standing_constraints``, ``response_schema`` and
    ``schema_id`` are retained only for compatibility with older callers. When a
    PromptCatalog is injected it is authoritative for every prompt layer.
    """

    request_id: str
    task: TaskType
    prompt_version: str
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
    identity_policy: str = ""
    standing_constraints: str = ""
    response_schema: str = ""
    schema_id: str = ""


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
    response: ValidatedResponse | None = None
    prompt_version: str = ""


class RagPipeline:
    """ADR-001: advisory orchestration; it never writes and never overrides the gate."""

    def __init__(
        self,
        retrieval: RetrievalAdapter,
        assembler: PromptAssembler,
        tutor: Tutor,
        validator: ResponseValidator,
        prompt_catalog: PromptCatalog | str | Path | None = None,
    ) -> None:
        self._retrieval = retrieval
        self._assembler = assembler
        self._tutor = tutor
        self._validator = validator
        self._prompt_catalog = (
            load_prompt_catalog(prompt_catalog)
            if isinstance(prompt_catalog, (str, Path))
            else prompt_catalog
        )

    def handle(self, request: RagRequest) -> RagResult:
        """Route, retrieve conditionally, assemble, call Tutor, and validate.

        Implements: ADR-005 §Decision and §Rejection codes; ADR-007 §Decision;
        FR-RAG-001, INV-CITE-001.
        """
        self._validate_request(request)
        catalog = self._resolve_catalog(request)

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
                return self._safe_abstained(
                    request=request,
                    catalog=catalog,
                    reason="retrieval_unavailable",
                    retrieval_performed=True,
                )

            if evidence.is_empty:
                return self._safe_abstained(
                    request=request,
                    catalog=catalog,
                    reason="no_evidence",
                    retrieval_performed=True,
                )

        try:
            task_schema = catalog.schema_for(request.task)
        except PromptCatalogError as exc:
            raise InvalidRequestError(
                "prompt catalog has no schema for the requested task"
            ) from exc

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
                prompt_version=catalog.version,
                identity_policy=catalog.identity_policy,
                standing_constraints=catalog.standing_constraints,
                response_schema=task_schema.text,
                learner_profile=request.learner_profile,
                resumable_state=request.resumable_state,
                evidence=prompt_evidence,
                history=request.history,
                current_turn=request.current_turn,
            )
        )

        try:
            tutor_result = self._generate(
                request=request,
                prompt=assembly.prompt,
                schema_id=task_schema.schema_id,
                temperature=0.0,
            )
        except TutorUnavailableError:
            return self._safe_abstained(
                request=request,
                catalog=catalog,
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
            return self._safe_rejected(
                request=request,
                catalog=catalog,
                reason="validator_error",
                retrieval_performed=retrieval_performed,
                evidence=evidence,
                prompt_tokens=assembly.token_count,
                tutor=tutor_result,
            )

        if verdict.accepted:
            return self._accepted(
                request=request,
                catalog=catalog,
                verdict=verdict,
                evidence=evidence,
                prompt_tokens=assembly.token_count,
                retrieval_performed=retrieval_performed,
                tutor=tutor_result,
            )

        if not self._can_repair(verdict):
            return self._final_validation_failure(
                request=request,
                catalog=catalog,
                verdict=verdict,
                evidence=evidence,
                prompt_tokens=assembly.token_count,
                retrieval_performed=retrieval_performed,
                tutor=tutor_result,
            )

        repair_prompt = self._build_repair_prompt(assembly.prompt, catalog, verdict)
        if (
            repair_prompt is None
            or estimate_tokens(repair_prompt) > self._assembler.config.token_budget
        ):
            return self._safe_rejected(
                request=request,
                catalog=catalog,
                reason="repair_budget_exceeded",
                retrieval_performed=retrieval_performed,
                evidence=evidence,
                prompt_tokens=assembly.token_count,
                validation=verdict,
                tutor=tutor_result,
            )

        try:
            repair_result = self._generate(
                request=request,
                prompt=repair_prompt,
                schema_id=task_schema.schema_id,
                temperature=0.0,
            )
        except TutorUnavailableError:
            return self._safe_rejected(
                request=request,
                catalog=catalog,
                reason="repair_tutor_unavailable",
                retrieval_performed=retrieval_performed,
                evidence=evidence,
                prompt_tokens=assembly.token_count,
                validation=verdict,
                tutor=tutor_result,
            )

        try:
            repair_verdict = self._validator.validate(
                request.task,
                repair_result.text,
                evidence,
            )
        except Exception:
            return self._safe_rejected(
                request=request,
                catalog=catalog,
                reason="validator_error",
                retrieval_performed=retrieval_performed,
                evidence=evidence,
                prompt_tokens=assembly.token_count,
                validation=verdict,
                tutor=repair_result,
            )

        if repair_verdict.accepted:
            return self._accepted(
                request=request,
                catalog=catalog,
                verdict=repair_verdict,
                evidence=evidence,
                prompt_tokens=assembly.token_count,
                retrieval_performed=retrieval_performed,
                tutor=repair_result,
            )

        return self._final_validation_failure(
            request=request,
            catalog=catalog,
            verdict=repair_verdict,
            evidence=evidence,
            prompt_tokens=assembly.token_count,
            retrieval_performed=retrieval_performed,
            tutor=repair_result,
        )

    def _generate(
        self,
        *,
        request: RagRequest,
        prompt: str,
        schema_id: str,
        temperature: float,
    ) -> TutorResult:
        return self._tutor.generate(
            TutorRequest(
                request_id=request.request_id,
                prompt=prompt,
                task=request.task,
                schema_id=schema_id,
                temperature=temperature,
            )
        )

    def _accepted(
        self,
        *,
        request: RagRequest,
        catalog: PromptCatalog,
        verdict: ValidationVerdict,
        evidence: EvidenceSet,
        prompt_tokens: int,
        retrieval_performed: bool,
        tutor: TutorResult,
    ) -> RagResult:
        validated_text = verdict.validated_text
        if not isinstance(validated_text, str) or not validated_text.strip():
            return self._safe_rejected(
                request=request,
                catalog=catalog,
                reason="validator_contract_violation",
                retrieval_performed=retrieval_performed,
                evidence=evidence,
                prompt_tokens=prompt_tokens,
                validation=verdict,
                tutor=tutor,
            )
        return RagResult(
            request_id=request.request_id,
            status="accepted",
            text=validated_text,
            evidence_ids=evidence.published_ids,
            prompt_tokens=prompt_tokens,
            retrieval_performed=retrieval_performed,
            validation=verdict,
            tutor=tutor,
            response=verdict.response,
            prompt_version=catalog.version,
        )

    def _final_validation_failure(
        self,
        *,
        request: RagRequest,
        catalog: PromptCatalog,
        verdict: ValidationVerdict,
        evidence: EvidenceSet,
        prompt_tokens: int,
        retrieval_performed: bool,
        tutor: TutorResult,
    ) -> RagResult:
        if verdict.code in ABSTENTION_CODES:
            return self._safe_abstained(
                request=request,
                catalog=catalog,
                reason=verdict.code,
                retrieval_performed=retrieval_performed,
                evidence=evidence,
                prompt_tokens=prompt_tokens,
                validation=verdict,
                tutor=tutor,
            )
        return self._safe_rejected(
            request=request,
            catalog=catalog,
            reason=verdict.code,
            retrieval_performed=retrieval_performed,
            evidence=evidence,
            prompt_tokens=prompt_tokens,
            validation=verdict,
            tutor=tutor,
        )

    def _can_repair(self, verdict: ValidationVerdict) -> bool:
        return verdict.repairable and verdict.code in SAFE_REPAIR_CODES

    def _build_repair_prompt(
        self,
        base_prompt: str,
        catalog: PromptCatalog,
        verdict: ValidationVerdict,
    ) -> str | None:
        try:
            repair = catalog.repair_template.format(
                code=verdict.code,
                error_path=verdict.error_path or "$",
                detail=verdict.detail or verdict.code,
            )
        except (KeyError, IndexError, ValueError):
            return None
        return f"{base_prompt}\n[repair_instruction]\n{repair}\n"

    def _safe_abstained(
        self,
        *,
        request: RagRequest,
        catalog: PromptCatalog,
        reason: str,
        retrieval_performed: bool,
        evidence: EvidenceSet | None = None,
        prompt_tokens: int = 0,
        validation: ValidationVerdict | None = None,
        tutor: TutorResult | None = None,
    ) -> RagResult:
        return RagResult(
            request_id=request.request_id,
            status="abstained",
            text=INSUFFICIENT_EVIDENCE_PHRASE,
            evidence_ids=evidence.published_ids if evidence is not None else (),
            prompt_tokens=prompt_tokens,
            retrieval_performed=retrieval_performed,
            validation=validation,
            tutor=tutor,
            reason=reason,
            prompt_version=catalog.version,
        )

    def _safe_rejected(
        self,
        *,
        request: RagRequest,
        catalog: PromptCatalog,
        reason: str,
        retrieval_performed: bool,
        evidence: EvidenceSet | None = None,
        prompt_tokens: int = 0,
        validation: ValidationVerdict | None = None,
        tutor: TutorResult | None = None,
    ) -> RagResult:
        return RagResult(
            request_id=request.request_id,
            status="rejected",
            text=SAFE_FALLBACK_MESSAGE,
            evidence_ids=evidence.published_ids if evidence is not None else (),
            prompt_tokens=prompt_tokens,
            retrieval_performed=retrieval_performed,
            validation=validation,
            tutor=tutor,
            reason=reason,
            prompt_version=catalog.version,
        )

    def _resolve_catalog(self, request: RagRequest) -> PromptCatalog:
        if self._prompt_catalog is not None:
            if request.prompt_version != self._prompt_catalog.version:
                raise InvalidRequestError(
                    "request prompt_version does not match the loaded prompt catalog"
                )
            return self._prompt_catalog

        schema_text = request.response_schema.strip()
        if not schema_text:
            prompt_path = DEFAULT_PROMPTS_DIR / f"{request.prompt_version}.yaml"
            if prompt_path.is_file():
                return load_prompt_catalog(prompt_path)
            raise InvalidRequestError(
                "no prompt catalog is configured and no prompt file matches "
                "the request prompt_version"
            )
        if not request.identity_policy.strip() or not request.standing_constraints.strip():
            raise InvalidRequestError(
                "identity_policy and standing_constraints are required when no "
                "prompt catalog is configured"
            )
        schema_id = request.schema_id.strip() or f"{request.task}.v1"
        return PromptCatalog(
            version=request.prompt_version,
            identity_policy=request.identity_policy,
            standing_constraints=request.standing_constraints,
            schemas=MappingProxyType(
                {
                    request.task: PromptSchema(
                        schema_id=schema_id,
                        text=schema_text,
                    )
                }
            ),
            repair_template=DEFAULT_REPAIR_TEMPLATE,
        )

    def _validate_request(self, request: RagRequest) -> None:
        required = (
            request.request_id,
            request.prompt_version,
            request.current_turn,
        )
        if any(not value.strip() for value in required):
            raise InvalidRequestError("required RagRequest text fields must be non-empty")
        if request.task not in ("conversation", "lesson_help", "writing_feedback"):
            raise InvalidRequestError(
                "task must be conversation, lesson_help or writing_feedback"
            )
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
