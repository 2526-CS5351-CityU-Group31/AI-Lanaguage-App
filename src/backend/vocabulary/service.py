"""VocabularyService - record per-user familiarity state and emit events.

Element: VocabularyService
Implements: FR-VOC-002; ADR-008 (emits vocabulary_reviewed events);
  ADR-009 / INV-AUTH-001 (owner-scoped only); S6 (sole writer of
  user_vocabulary)
Never exposes another learner's vocabulary state: every read/write is scoped to
the authenticated user id supplied by AuthSecurity.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.backend.contracts.models import Familiarity

_VALID_STATES = {state.value for state in Familiarity}


class VocabularyStateError(Exception):
    """An unknown familiarity state was supplied.

    Implements: FR-VOC-002 (only learning/familiar/mastered)
    """

    status_code: int = 422

    def __init__(self, state: str) -> None:
        self.state = state
        self.body = {"state": "must be one of learning, familiar, mastered"}
        super().__init__(f"invalid familiarity state: {state!r}")


@dataclass(frozen=True)
class FamiliarityRecord:
    """Current familiarity state for one vocabulary entry.

    Implements: FR-VOC-002
    """

    user_id: str
    entry_id: str
    state: str


class VocabularyService:
    """Owner-scoped familiarity state writer.

    Implements: FR-VOC-002; ADR-008; INV-AUTH-001; S6
    """

    def __init__(self, stores: object) -> None:
        self._stores = stores

    def record_familiarity(
        self,
        *,
        user_id: str,
        entry_id: str,
        state: str,
    ) -> FamiliarityRecord:
        """Set familiarity state and emit a ``vocabulary_reviewed`` event.

        Implements: FR-VOC-002; ADR-008; INV-AUTH-001 (owner-scoped)
        """
        if state not in _VALID_STATES:
            raise VocabularyStateError(state)

        store = getattr(self._stores, "vocabulary", None)
        if store is None:
            raise RuntimeError("vocabulary store is not configured")
        store.set_state(user_id=user_id, entry_id=entry_id, state=state)

        events = getattr(self._stores, "events", None)
        if events is not None:
            events.append(
                user_id=user_id,
                event_type="vocabulary_reviewed",
                payload={"entry_id": entry_id, "state": state},
                idempotency_key=f"{entry_id}:{state}",
            )
        return FamiliarityRecord(user_id=user_id, entry_id=entry_id, state=state)

    def get_familiarity(self, *, user_id: str, entry_id: str) -> FamiliarityRecord | None:
        """Read one entry's familiarity for the owner only.

        Implements: FR-VOC-002; INV-AUTH-001 (owner-scoped)
        """
        store = getattr(self._stores, "vocabulary", None)
        if store is None:
            raise RuntimeError("vocabulary store is not configured")
        state = store.get_state(user_id=user_id, entry_id=entry_id)
        if state is None:
            return None
        return FamiliarityRecord(user_id=user_id, entry_id=entry_id, state=state)
