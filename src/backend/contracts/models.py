"""Typed DTOs and enums shared across the backend.

Support package (not an architectural element). Contains no domain decision.

Implements: ADR-009 (learner data shapes); INV-LANG-001, INV-CEFR-001 (canonical
  language and CEFR enums); FR-AUTH-001, FR-PROF-001 (profile/user shape)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final

SUPPORTED_LANGUAGE: Final[str] = "en"


class CefrLevel(str, Enum):
    """Canonical CEFR levels accepted at the API boundary.

    Implements: INV-CEFR-001
    """

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(level.value for level in cls)


class Familiarity(str, Enum):
    """Vocabulary familiarity state.

    Implements: FR-VOC-002
    """

    LEARNING = "learning"
    FAMILIAR = "familiar"
    MASTERED = "mastered"


@dataclass
class UserRecord:
    """Stored user row (owner-scoped).

    Implements: ADR-009 (users written by AuthSecurity); FR-AUTH-001
    """

    user_id: str
    email: str
    password_hash: str
    cefr_level: str
    language: str = SUPPORTED_LANGUAGE
    learning_goals: str | None = None
    salt: str = ""


@dataclass(frozen=True)
class Principal:
    """The authenticated identity, derived only from a session.

    Implements: INV-AUTH-001; ADR-009 (principal from session only)
    """

    user_id: str
    email: str


@dataclass(frozen=True)
class Profile:
    """Learner-visible profile projection (owner only).

    Implements: FR-PROF-001; ADR-009
    """

    user_id: str
    email: str
    cefr_level: str
    language: str
    learning_goals: str | None = None


@dataclass
class RegistrationResult:
    """Outcome of a successful registration (token only, never the hash).

    Implements: FR-AUTH-001
    """

    session_token: str
    profile: Profile = field(repr=False)


class LearnerMode(str, Enum):
    """Frontend learner-mode selector for a chat turn.

    Implements: FR-CHAT-001; INV-SCOPE-001 (mode selects tutor task, never
      bypasses scope control)
    """

    TEXT = "text"
    CONVERSATION_PRACTICE = "conversation_practice"
    WRITING_FEEDBACK = "writing_feedback"
    GRAMMAR_QUESTION = "grammar_question"
    VOCABULARY_QUESTION = "vocabulary_question"
    LESSON_QUESTION = "lesson_question"


# Frontend learner_mode -> backend tutor task mapping (ADR-005 contracts).
LEARNER_MODE_TO_TASK: Final[dict[str, str]] = {
    LearnerMode.TEXT.value: "conversation",
    LearnerMode.CONVERSATION_PRACTICE.value: "conversation",
    LearnerMode.WRITING_FEEDBACK.value: "writing_feedback",
    LearnerMode.GRAMMAR_QUESTION.value: "lesson_help",
    LearnerMode.VOCABULARY_QUESTION.value: "lesson_help",
    LearnerMode.LESSON_QUESTION.value: "lesson_help",
}
