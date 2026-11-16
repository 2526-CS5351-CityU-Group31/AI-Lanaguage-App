"""Chat pipeline factory - wires the real RagPipeline with a Noop fallback.

Element: AppEntry support (transport composition). Not an SSOT module.

Implements: FR-CHAT-001; ADR-001 (advisory pipeline), ADR-005 (validated
  contract), ADR-006 (assembled prompt), ADR-007 (conditional retrieval);
  INV-SCOPE-001/003 (scope already ran before this is called), INV-CITE-001
  (CitationValidator vetoes output).

Design notes
------------
Leon's ``ai_companion`` modules import via the ``backend.*`` package (i.e. the
``src/`` directory is on ``sys.path``), while the API uses ``src.backend.*``.
To bridge without duplicating modules we add ``src`` to ``sys.path`` here and
import ``backend.*`` lazily at construction time. When no ``LLM_API_KEY`` is
configured (or the pipeline cannot be built) we return the deterministic
``_NoopPipeline`` so the API keeps working offline (RP-004 safe degradation).

The only real retrieval backend (pgvector ``RetrievalService``) is not built
yet, so grounded/lesson questions abstain inside RagPipeline; ``conversation``
turns do not require grounding and are answered by the live model.
"""

from __future__ import annotations

import os
import sys
from typing import Any

_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class NoopPipeline:
    """Deterministic stub used when the real pipeline is unavailable.

    Implements: FR-CHAT-001 (offline-safe fallback); RP-004
    """

    def run(self, **kwargs: object) -> dict:
        task = kwargs.get("task", "conversation")
        return {
            "task": task,
            "abstained": False,
            "source_ids": [],
            "answer": "Hello! How can I help you practise English?",
            "validation_id": "val_" + str(kwargs.get("request_id", "turn")),
        }


class _EmptyRetrievalService:
    """Placeholder RetrievalService: no corpus search yet -> abstain gracefully.

    Implements: ADR-007 (published-only retrieval); INV-SCOPE-006. Replaced when
    a pgvector-backed RetrievalService lands (database lane).
    """

    def search(self, query: object) -> list:
        return []


class RagPipelineAdapter:
    """Adapt RagPipeline(RagRequest)->RagResult to the ChatRouter dict contract.

    Implements: FR-CHAT-001; ADR-005; INV-CITE-001 (validator veto)
    """

    def __init__(self, pipeline: Any, *, level: str = "A2") -> None:
        self._pipeline = pipeline
        self._level = level

    def run(self, **kwargs: object) -> dict:
        task = str(kwargs.get("task", "conversation"))
        # RagPipeline supports conversation/lesson_help; other frontend modes map
        # to conversation so the model still answers without a grounded contract.
        rag_task = task if task in ("conversation", "lesson_help") else "conversation"
        request = _build_rag_request(
            request_id=str(kwargs.get("request_id", "turn")),
            task=rag_task,
            message=str(kwargs.get("message", "")),
            requires_grounding=bool(kwargs.get("requires_grounding", False)),
            topic=kwargs.get("topic"),
            level=self._level,
        )
        try:
            result = self._pipeline.handle(request)
        except Exception:
            return NoopPipeline().run(**kwargs)

        if result.status == "accepted" and result.text:
            return {
                "task": task,
                "abstained": False,
                "source_ids": list(result.evidence_ids),
                "answer": result.text,
                "validation_id": getattr(result.validation, "validation_id", None)
                or ("val_" + request.request_id),
            }
        # Abstained or rejected -> a safe, non-leaking fallback answer.
        return {
            "task": task,
            "abstained": True,
            "source_ids": list(result.evidence_ids),
            "answer": result.text
            or "I don't have enough verified lesson evidence to answer that yet.",
            "validation_id": "val_" + request.request_id,
        }


def _build_rag_request(*, request_id, task, message, requires_grounding, topic, level):
    from backend.ai_companion.rag_pipeline import RagRequest  # lazy: backend.* tree

    return RagRequest(
        request_id=request_id,
        task=task,
        prompt_version="prompt_v1.0.0",
        identity_policy=(
            "You are a friendly English tutor for CEFR A1-B2 learners. "
            "Reply only in English about language learning."
        ),
        standing_constraints=(
            "Only help with English language learning. Never invent lesson "
            "citations. Keep answers short and level-appropriate."
        ),
        response_schema='{"task": "conversation", "abstained": bool, '
        '"source_ids": [], "answer": "string", "follow_up": "string"}',
        schema_id=f"{task}_v1",
        learner_profile=f"CEFR level {level}; target language English.",
        resumable_state="",
        history=(),
        current_turn=message,
        requires_grounding=requires_grounding,
        query=message if requires_grounding else "",
        language="en",
        level=level,
        topic=topic,
        top_k=5,
    )


def build_pipeline_factory(api_key: str | None = None, level: str = "A2"):
    """Return a zero-arg callable producing the best available pipeline.

    Implements: FR-CHAT-001; RP-004 (safe fallback); S5 (no env read here - the
    caller passes ``api_key`` from the config module).
    Returns a factory for ``RagPipelineAdapter`` when ``api_key`` is set and the
    real modules import cleanly, otherwise a factory for ``NoopPipeline``.
    """
    api_key = (api_key or "").strip()
    if not api_key:
        return lambda: NoopPipeline()

    if _SRC_DIR not in sys.path:
        sys.path.insert(0, _SRC_DIR)

    try:
        from backend.ai_companion.prompt_assembly import PromptAssembler
        from backend.ai_companion.provider_gateway import CityUModelGateway, UrllibHttpTransport
        from backend.ai_companion.rag_pipeline import RagPipeline
        from backend.ai_companion.retrieval_adapter import RetrievalAdapter
        from backend.ai_companion.tutor import Tutor
        from backend.config import ProviderGatewayConfig
        from backend.safety_boundary.citation_validator import CitationValidator

        gateway = CityUModelGateway(
            config=ProviderGatewayConfig(api_key=api_key),
            transport=UrllibHttpTransport(),
        )
        pipeline = RagPipeline(
            retrieval=RetrievalAdapter(_EmptyRetrievalService()),
            assembler=PromptAssembler(),
            tutor=Tutor(gateway),
            validator=CitationValidator(),
        )
        return lambda: RagPipelineAdapter(pipeline, level=level)
    except Exception:  # pragma: no cover - environment dependent
        return lambda: NoopPipeline()
