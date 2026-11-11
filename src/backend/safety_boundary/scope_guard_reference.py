"""ScopeGuard reference adapter - a deterministic, stdlib-only classifier for
dev/offline wiring.

Element: ScopeGuard (reference adapter, NOT the gate module)
Implements: INV-SCOPE-001, INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005;
  NFR-QUAL-004

================================================================================
This is a REFERENCE implementation so the chat path can run in dev/offline
without touching the human-authored gate file ``scope_guard.py``. It is NOT the
production authority: the human author owns ``scope_guard.py`` and must replace
this with the reviewed classifier. It is keyword-based and deterministic; it
makes NO model or vector calls (C4).
================================================================================
"""

from __future__ import annotations

import re

from src.backend.safety_boundary.scope_guard import ScopeGuard, ScopeResult

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

_ACTION_VERBS = re.compile(r"\b(book|buy|order|download|send|hack|find|search|play)\b", re.IGNORECASE)


class ReferenceScopeGuard(ScopeGuard):
    """Deterministic keyword classifier (reference only).

    Implements: INV-SCOPE-001/002/004/005; NFR-QUAL-004
    """

    def __init__(self) -> None:  # noqa: D401 - intentionally no gate check
        pass

    def _words(self, message: str) -> set[str]:
        return set(re.findall(r"[a-z']+", message.lower()))

    def classify(self, message: str) -> ScopeResult:
        """Classify by educational vs off-topic signals (deterministic).

        Implements: INV-SCOPE-002 (fixed refusal on off-topic);
          INV-SCOPE-004 (fixed clarification on empty/ambiguous);
          INV-SCOPE-005 (mixed when an unsupported action is combined);
          INV-SCOPE-001 (scope precedes any downstream call)
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
