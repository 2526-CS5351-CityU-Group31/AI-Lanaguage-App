"""ScopeGuard - deterministic intent gate before retrieval/model.

================================================================================
HUMAN-AUTHORED GATE MODULE (permission-model.md §2; role-ownership.md).
Element: ScopeGuard
Implements: ADR-005; INV-SCOPE-001, INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005;
  NFR-QUAL-004
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


# Educational signals: expanded with morphology & grammar comparison tokens
_EDUCATIONAL = {
    "grammar", "vocabulary", "word", "sentence", "writing", "tense",
    "verb", "noun", "adjective", "pronoun", "spelling", "pronounce", "meaning",
    "definition", "translate", "translation", "example", "lesson", "practice",
    "english", "learn", "learning", "speak", "read", "reading", "listen",
    "essay", "paragraph", "correct", "correction", "phrase", "idiom", "preposition",
    "difference", "between", "usage", "vs", "affect", "effect",
}

# Strong off-topic markers: code/tech, finance, trivia, etc.
_OFF_TOPIC = {
    "weather", "stock", "crypto", "bitcoin", "recipe", "cook", "football",
    "basketball", "movie", "film", "song", "celebrity", "politics", "election",
    "medical", "diagnose", "medicine", "lawyer", "lawsuit", "hack", "password",
    "bomb", "weapon", "drug", "script", "scrape", "python", "javascript", "code",
    "database", "sql", "server", "algorithm",
}

_GROUNDING = {
    "grammar", "tense", "rule", "lesson", "mean", "meaning", "definition",
    "difference", "between", "usage",
}

# Distinguish coding/system actions
_TECH_ACTION = re.compile(
    r"\b(write a script|write code|scrape|write a program|build an app)\b",
    re.IGNORECASE,
)
_ACTION_VERBS = re.compile(
    r"\b(book|buy|order|download|send|hack|find|search|play)\b",
    re.IGNORECASE,
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

        # 1. Immediate rejection for technical/coding generation requests
        if _TECH_ACTION.search(text):
            return ScopeResult(status="rejected", reason="off_topic")

        words = self._words(text)
        has_edu = bool(words & _EDUCATIONAL)
        has_off = bool(words & _OFF_TOPIC)
        has_action = bool(_ACTION_VERBS.search(text))

        # 2. Pure off-topic rejection
        if has_off and not has_edu:
            return ScopeResult(status="rejected", reason="off_topic")

        # 3. If off-topic terms dominate technical actions, reject rather than mix
        if has_off and has_edu:
            # If it explicitly hits tech/finance terms, treat as rejected
            if any(w in words for w in {"script", "scrape", "python", "bitcoin", "crypto"}):
                return ScopeResult(status="rejected", reason="off_topic")
            return ScopeResult(status="mixed", reason="partial_off_topic")

        if has_action and not has_edu:
            return ScopeResult(status="rejected", reason="unsupported_action")
        if has_action and has_edu:
            return ScopeResult(status="mixed", reason="action_plus_edu")

        if not has_edu:
            return ScopeResult(status="uncertain", reason="ambiguous")

        requires_grounding = bool(words & _GROUNDING)
        return ScopeResult(
            status="accepted",
            requires_grounding=requires_grounding,
            reason="educational",
        )