"""ChatRouter - chat HTTP boundary; persists only validated turns and never
runs retrieval/LLM after a deterministic scope rejection.

Element: ChatRouter
Implements: INV-SCOPE-001, INV-SCOPE-003; FR-CHAT-001; ADR-005 (validated
  response contract); ADR-008 (emit turn/session events); ADR-009 (owner-scoped)

Ordering guarantee (INV-SCOPE-001 / INV-SCOPE-003): the ScopeGuard runs first.
If the turn is rejected/uncertain/mixed, this router returns the fixed
scope response and makes ZERO retrieval or tutor calls. No model text is
displayed or persisted before a deterministic verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.backend.auth.security import AuthenticationError
from src.backend.contracts.models import LEARNER_MODE_TO_TASK, Principal

# Approved fixed scope strings (INV-SCOPE-002 / INV-SCOPE-004 / INV-SCOPE-005).
FIXED_REFUSAL = "I'm sorry, but I can only help with language-learning questions."
FIXED_CLARIFICATION = (
    "Could you clarify your language-learning question? Please ask about "
    "English grammar, vocabulary, writing, or practice."
)
FIXED_RESUBMIT = (
    "I can only help with the language-learning part. Please resubmit just "
    "your language-learning question."
)


@dataclass(frozen=True)
class ScopeVerdict:
    """Deterministic scope result for one message.

    Implements: INV-SCOPE-001, INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005
    """

    status: str  # accepted | rejected | uncertain | mixed
    requires_grounding: bool = False


@dataclass(frozen=True)
class ChatTurn:
    """A completed, validated chat turn.

    Implements: FR-CHAT-001
    """

    session_id: str
    turn_id: str
    response: dict
    source_ids: tuple[str, ...] = ()


class ChatRouter:
    """Chat boundary: scope first, then (and only then) the tutor pipeline.

    Implements: INV-SCOPE-001, INV-SCOPE-003; FR-CHAT-001; ADR-005
    """

    def __init__(self, security: object, scope_guard: object, pipeline_factory) -> None:
        self._security = security
        self._scope_guard = scope_guard
        self._make_pipeline = pipeline_factory

    def _principal(self, token: str) -> Principal:
        principal = self._security.resolve_principal(token)
        if principal is None:
            raise AuthenticationError("invalid session")
        return principal

    def handle_message(
        self,
        token: str,
        *,
        session_id: str,
        message: str,
        request_id: str,
        learner_mode: str = "text",
        topic: str | None = None,
    ) -> dict:
        """Scope-gate the message, then hand accepted turns to the pipeline.

        Implements: INV-SCOPE-001 (scope precedes retrieval/model);
          INV-SCOPE-003 (zero calls on rejection); INV-SCOPE-002/004/005
          (fixed strings); FR-CHAT-001

        Returns a FLAT frontend-compatible dict (task/abstained/source_ids/
        answer/validation_id, optional scope_status/scope_message). The
        learner_mode selects the tutor task via LEARNER_MODE_TO_TASK but never
        bypasses the deterministic scope gate.
        """
        self._principal(token)

        # INV-SCOPE-001: scope control runs before any downstream call.
        verdict: ScopeVerdict = self._scope_guard.classify(message)

        if verdict.status == "rejected":
            return {
                "scope_status": "rejected",
                "scope_message": FIXED_REFUSAL,
                "answer": "",
                "source_ids": [],
            }
        if verdict.status == "uncertain":
            return {
                "scope_status": "uncertain",
                "scope_message": FIXED_CLARIFICATION,
                "answer": "",
                "source_ids": [],
            }
        if verdict.status == "mixed":
            return {
                "scope_status": "mixed",
                "scope_message": FIXED_RESUBMIT,
                "answer": "",
                "source_ids": [],
            }

        # Accepted: only now may retrieval/tutor run.
        task = LEARNER_MODE_TO_TASK.get(learner_mode, "conversation")
        pipeline = self._make_pipeline()
        result = pipeline.run(
            session_id=session_id,
            message=message,
            request_id=request_id,
            requires_grounding=verdict.requires_grounding,
            task=task,
            topic=topic,
        )
        return {
            "task": result.get("task", task),
            "abstained": bool(result.get("abstained", False)),
            "source_ids": list(result.get("source_ids", [])),
            "answer": result.get("answer", ""),
            "validation_id": result.get("validation_id", request_id),
            "scope_status": "accepted",
            **({"follow_up": result["follow_up"]} if "follow_up" in result else {}),
            **({"tips": result["tips"]} if "tips" in result else {}),
            **({"suggested_text": result["suggested_text"]} if "suggested_text" in result else {}),
            **({"explanation": result["explanation"]} if "explanation" in result else {}),
            **({"examples": result["examples"]} if "examples" in result else {}),
            **({"sources": result["sources"]} if "sources" in result else {}),
        }
