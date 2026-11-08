"""ScopeGuard - deterministic intent gate before retrieval/model.

================================================================================
HUMAN-AUTHORED GATE MODULE (permission-model.md §2; role-ownership.md).
Element: ScopeGuard
Implements: ADR-005 (validated response contract); INV-SCOPE-001,
  INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005; NFR-QUAL-004

Contract:
  - classify(message) -> ScopeResult is deterministic and bounded; it must
    NOT call any LLM or vector store (safety_boundary is stdlib-only, C4).
  - status is one of: "accepted", "rejected", "uncertain", "mixed".
  - rejected returns the exact FIXED_REFUSAL string with zero model tokens.
  - uncertain returns the fixed clarification; mixed the fixed resubmit.
  - accepted may set requires_grounding for lesson/grammar questions.
================================================================================
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
class ScopeResult:
    """Deterministic scope verdict.

    Implements: INV-SCOPE-001, INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005
    """

    status: str
    requires_grounding: bool = False
    reason: str = ""


_EDUCATIONAL = {
    "grammar", "vocabulary", "word", "sentence", "write", "writing", "tense",
    "verb", "noun", "adjective", "pronoun", "spelling", "pronounce", "meaning",
    "definition", "translate", "translation", "example", "lesson", "practice",
    "english", "learn", "learning", "speak", "read", "reading", "listen",
    "essay", "paragraph", "correct", "correction", "phrase", "idiom", "preposition",
}

# Explicit off-topic request markers (deterministic, unambiguous).
_OFF_TOPIC = {
    "weather", "stock", "crypto", "bitcoin", "recipe", "cook", "football",
    "basketball", "movie", "film", "song", "celebrity", "politics", "election",
    "medical", "diagnose", "medicine", "lawyer", "lawsuit", "hack", "password",
    "bomb", "weapon", "drug",
}

_GROUNDING = {"grammar", "tense", "rule", "lesson", "mean", "meaning", "definition"}

_ACTION_VERBS = re.compile(
    r"\b(book|buy|order|download|send|hack|find|search|play)\b", re.IGNORECASE
)


class ScopeGuard:
    """Deterministic intent classifier (Human-Authored Gate Module).

    Implements: INV-SCOPE-001/002/004/005; NFR-QUAL-004
    """

    def __init__(self) -> None:
        """Initialize deterministic scope classifier."""
        pass

    def _words(self, message: str) -> set[str]:
        return set(re.findall(r"[a-z']+", message.lower()))

    def classify(self, message: str) -> ScopeResult:
        """Classify by educational vs off-topic signals (deterministic).

        Implements:
          - INV-SCOPE-002 (fixed refusal on off-topic)
          - INV-SCOPE-004 (fixed clarification on empty/ambiguous)
          - INV-SCOPE-005 (mixed when an unsupported action is combined)
          - INV-SCOPE-001 (scope precedes any downstream call)
        """
        text = message.strip()
        if not text:
            return ScopeResult(status="uncertain", reason="empty")

        words = self._words(text)
        has_edu = bool(words & _EDUCATIONAL)
        has_off = bool(words & _OFF_TOPIC)
        has_action = bool(_ACTION_VERBS.search(text))

        if has_off and not has_edu:
            return ScopeResult(status="rejected", reason="off_topic")
        if has_off and has_edu:
            return ScopeResult(status="mixed", reason="partial_off_topic")
        if has_action and not has_edu:
            return ScopeResult(status="rejected", reason="unsupported_action")
        if has_action and has_edu:
            return ScopeResult(status="mixed", reason="action_plus_edu")
        if not has_edu:
            # No clear educational signal and not clearly off-topic.
            return ScopeResult(status="uncertain", reason="ambiguous")

        requires_grounding = bool(words & _GROUNDING)
        return ScopeResult(
            status="accepted",
            requires_grounding=requires_grounding,
            reason="educational",
        )