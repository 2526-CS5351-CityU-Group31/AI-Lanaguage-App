"""Data access primitives (connections, unit of work, repositories).

Support package (not an architectural element). Only domain services touch
repositories; no model code may reach this package.

Implements: ADR-009 (owner-scoped repositories); structural-constraints.md S6
  (single writer per store); INV-SEC-001 (runtime vector access is read-only -
  this module holds no content write path)
"""

from __future__ import annotations

from typing import Protocol

from src.backend.contracts.models import UserRecord


class UserRepository(Protocol):
    """Owner-scoped user store contract.

    Implements: ADR-009 (users written by AuthSecurity); S6
    """

    def get_by_email(self, email: str) -> UserRecord | None: ...

    def get_by_id(self, user_id: str) -> UserRecord | None: ...

    def all_records(self) -> dict[str, UserRecord]: ...

    def add(self, record: UserRecord) -> None: ...

    def update(self, record: UserRecord) -> None: ...


class SessionRepository(Protocol):
    """Session token store contract (tokens stored hashed).

    Implements: FR-AUTH-001; ADR-009 (principal from session only)
    """

    def issue(self, token_hash: str, user_id: str) -> None: ...

    def resolve(self, token_hash: str) -> str | None: ...

    def revoke(self, token_hash: str) -> None: ...

    def all_records(self) -> dict[str, str]: ...


class InMemoryUserRepository:
    """Deterministic in-memory user repository for offline/dev.

    Implements: ADR-009; S6 (single writer). Not used in production.
    """

    def __init__(self) -> None:
        self._by_email: dict[str, UserRecord] = {}
        self._by_id: dict[str, UserRecord] = {}

    def get_by_email(self, email: str) -> UserRecord | None:
        return self._by_email.get(email.lower())

    def get_by_id(self, user_id: str) -> UserRecord | None:
        return self._by_id.get(user_id)

    def all_records(self) -> dict[str, UserRecord]:
        return dict(self._by_id)

    def add(self, record: UserRecord) -> None:
        self._by_email[record.email.lower()] = record
        self._by_id[record.user_id] = record

    def update(self, record: UserRecord) -> None:
        self._by_email[record.email.lower()] = record
        self._by_id[record.user_id] = record


class InMemorySessionRepository:
    """Deterministic in-memory session repository for offline/dev.

    Implements: FR-AUTH-001; ADR-009
    """

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}

    def issue(self, token_hash: str, user_id: str) -> None:
        self._sessions[token_hash] = user_id

    def resolve(self, token_hash: str) -> str | None:
        return self._sessions.get(token_hash)

    def revoke(self, token_hash: str) -> None:
        self._sessions.pop(token_hash, None)

    def all_records(self) -> dict[str, str]:
        return dict(self._sessions)


class InMemoryVocabularyStore:
    """Per-user familiarity state (owner-scoped).

    Implements: FR-VOC-002; ADR-009 (owner-scoped reads/writes); S6
    """

    def __init__(self) -> None:
        self._state: dict[tuple[str, str], str] = {}

    def set_state(self, *, user_id: str, entry_id: str, state: str) -> None:
        self._state[(user_id, entry_id)] = state

    def get_state(self, user_id: str, entry_id: str) -> str | None:
        return self._state.get((user_id, entry_id))

    def count_state(self, user_id: str, state: str) -> int:
        return sum(1 for (uid, _eid), s in self._state.items() if uid == user_id and s == state)


class InMemoryEventStore:
    """Append-only learning events with idempotency keys.

    Implements: ADR-008 (append-only, idempotent); INV-PROG-001; S6
    """

    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._keys: set[tuple[str, str]] = set()

    def append(
        self,
        *,
        user_id: str,
        event_type: str,
        payload: dict,
        idempotency_key: str,
    ) -> None:
        key = (user_id, idempotency_key)
        if key in self._keys:
            return
        self._keys.add(key)
        self._rows.append(
            {
                "user_id": user_id,
                "event_type": event_type,
                "payload": dict(payload),
                "idempotency_key": idempotency_key,
            }
        )

    def for_user(self, user_id: str) -> list[dict]:
        return [dict(row) for row in self._rows if row["user_id"] == user_id]


class InMemoryStores:
    """Container wiring the in-memory repositories for tests/dev.

    Implements: ADR-009; S6
    """

    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.sessions = InMemorySessionRepository()
        self.vocabulary = InMemoryVocabularyStore()
        self.events = InMemoryEventStore()
        self.loader = None  # set by the composition root when a dataset is available
