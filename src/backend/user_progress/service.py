"""ProgressService - event-sourced dashboard aggregation.

Element: ProgressService
Implements: INV-PROG-001, FR-DASH-001; ADR-008 (append-only events,
  read-time projection); ADR-009 (owner-scoped); S6 (sole writer of
  learning_events)

Dashboard totals are computed ONLY from stored ``learning_events`` rows, never
from model output. Every query is scoped to the authenticated user id.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DashboardMetrics:
    """Deterministic, non-negative progress aggregates for one learner.

    Implements: FR-DASH-001; INV-PROG-001
    """

    sessions: int
    words_reviewed: int
    mastered_vocabulary: int
    recent_topics: list[str] = field(default_factory=list)


class ProgressService:
    """Append events and project dashboard totals for the owner only.

    Implements: INV-PROG-001; FR-DASH-001; ADR-008; S6
    """

    def __init__(self, stores: object) -> None:
        self._stores = stores

    def record_event(
        self,
        *,
        user_id: str,
        event_type: str,
        payload: dict | None = None,
        idempotency_key: str,
    ) -> None:
        """Append one immutable learning event (idempotent by key).

        Implements: ADR-008 (append-only, idempotent); S6
        """
        events = getattr(self._stores, "events", None)
        if events is None:
            raise RuntimeError("event store is not configured")
        events.append(
            user_id=user_id,
            event_type=event_type,
            payload=payload or {},
            idempotency_key=idempotency_key,
        )

    def dashboard(self, *, user_id: str) -> DashboardMetrics:
        """Project totals directly from stored events for the owner.

        Implements: INV-PROG-001 (counts match stored events); FR-DASH-001
        """
        events = getattr(self._stores, "events", None)
        if events is None:
            raise RuntimeError("event store is not configured")
        rows = events.for_user(user_id)

        sessions = sum(1 for e in rows if e["event_type"] == "session_started")
        words_reviewed = sum(1 for e in rows if e["event_type"] == "vocabulary_reviewed")
        recent_topics = sorted(
            {
                e["payload"].get("topic")
                for e in rows
                if e["event_type"] == "turn_completed" and e["payload"].get("topic")
            }
        )

        vocabulary = getattr(self._stores, "vocabulary", None)
        mastered = 0
        if vocabulary is not None:
            mastered = vocabulary.count_state(user_id, "mastered")

        return DashboardMetrics(
            sessions=sessions,
            words_reviewed=words_reviewed,
            mastered_vocabulary=mastered,
            recent_topics=list(recent_topics),
        )
