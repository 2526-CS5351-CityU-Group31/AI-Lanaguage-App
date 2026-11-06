"""ScopeGuard - deterministic intent gate before retrieval/model.

================================================================================
HUMAN-AUTHORED GATE MODULE (permission-model.md §2; role-ownership.md).
The Build agent has NO access to this file. The interface, constants and
docstrings below are a scaffold written for a human author to implement.
Do not ship until a human author + ADR reference + failing-before/passing-after
test + two reviewers have signed off (.agent/rules.md §4).
================================================================================

Element: ScopeGuard
Implements: ADR-005 (validated response contract); INV-SCOPE-001,
  INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005; NFR-QUAL-004

Contract:
  - ``classify(message) -> ScopeResult`` is deterministic and bounded; it must
    NOT call any LLM or vector store (safety_boundary is stdlib-only, C4).
  - status is one of: ``accepted``, ``rejected``, ``uncertain``, ``mixed``.
  - ``rejected`` returns the exact FIXED_REFUSAL string with zero model tokens.
  - ``uncertain`` returns the fixed clarification; ``mixed`` the fixed resubmit.
  - ``accepted`` may set ``requires_grounding`` for lesson/grammar questions.
"""

from __future__ import annotations

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


class ScopeGuard:
    """Deterministic intent classifier. Implementation is human-authored.

    Implements: INV-SCOPE-001/002/004/005; NFR-QUAL-004
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "ScopeGuard is a human-authored gate module; see module docstring."
        )

    def classify(self, message: str) -> ScopeResult:
        """Classify a message into accepted/rejected/uncertain/mixed.

        Implements: INV-SCOPE-001, INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005;
          NFR-QUAL-004
        """
        raise NotImplementedError
