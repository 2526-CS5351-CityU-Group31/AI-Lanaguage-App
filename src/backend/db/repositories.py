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


class InMemoryChatSessionStore:
    """Server-generated chat session id -> owner user_id (owner-scoped).

    Implements: FR-CHAT-001; ADR-009 (a session belongs to its owner); the id
    is always server-generated, never client-supplied.
    """

    def __init__(self) -> None:
        self._owner: dict[str, str] = {}

    def create(self, session_id: str, user_id: str) -> None:
        self._owner[session_id] = user_id

    def owner_of(self, session_id: str) -> str | None:
        return self._owner.get(session_id)


class InMemoryStores:
    """Container wiring the in-memory repositories for tests/dev.

    Implements: ADR-009; S6
    """

    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.sessions = InMemorySessionRepository()
        self.vocabulary = InMemoryVocabularyStore()
        self.events = InMemoryEventStore()
        self.chat_sessions = InMemoryChatSessionStore()
        self.loader = None  # set by the composition root when a dataset is available


# ==========================================================================
# PostgreSQL repositories (production). Same synchronous interface as the
# in-memory implementations above, so services and routers are unchanged.
#
# Implements: ADR-009 (owner-scoped), ADR-008 (append-only events),
#   INV-PROG-001, INV-AUTH-001, INV-SEC-001 (no corpus write path here),
#   S6 (single writer per store), ADR-011 (Render managed Postgres)
# ==========================================================================

try:  # imported lazily so offline tests without psycopg still run
    import psycopg
    import psycopg_pool
except Exception:  # pragma: no cover - import guard
    psycopg = None  # type: ignore[assignment]
    psycopg_pool = None  # type: ignore[assignment]

from src.backend.contracts.models import UserRecord


class PostgresUserRepository:
    """Owner-scoped user store on PostgreSQL.

    Implements: ADR-009; S6; INV-AUTH-001 (never returns another owner's rows
    through a caller-supplied id - lookups are by session-derived id)
    """

    def __init__(self, pool: "psycopg_pool.ConnectionPool") -> None:
        self._pool = pool

    @staticmethod
    def _row_to_record(row: dict) -> UserRecord:
        return UserRecord(
            user_id=str(row["user_id"]),
            email=row["email"],
            password_hash=row["password_hash"],
            salt=row["salt"],
            cefr_level=row["cefr_level"],
            language=row["language"],
            learning_goals=row["learning_goals"],
        )

    def get_by_email(self, email: str) -> UserRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT user_id, email, password_hash, salt, cefr_level, language,"
                " learning_goals FROM users WHERE email = %s",
                (email.lower(),),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def get_by_id(self, user_id: str) -> UserRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT user_id, email, password_hash, salt, cefr_level, language,"
                " learning_goals FROM users WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def all_records(self) -> dict[str, UserRecord]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT user_id, email, password_hash, salt, cefr_level, language,"
                " learning_goals FROM users"
            ).fetchall()
        return {str(r["user_id"]): self._row_to_record(r) for r in rows}

    def add(self, record: UserRecord) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO users (user_id, email, password_hash, salt, cefr_level,"
                " language, learning_goals) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    record.user_id,
                    record.email.lower(),
                    record.password_hash,
                    record.salt,
                    record.cefr_level,
                    record.language,
                    record.learning_goals,
                ),
            )

    def update(self, record: UserRecord) -> None:
        # CEFR/language CHECK constraints are enforced by the schema (INV-LANG/CEFR).
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE users SET cefr_level = %s, language = %s, learning_goals = %s"
                " WHERE user_id = %s",
                (
                    record.cefr_level,
                    record.language,
                    record.learning_goals,
                    record.user_id,
                ),
            )


class PostgresSessionRepository:
    """Session token store on PostgreSQL (tokens stored hashed).

    Implements: FR-AUTH-001; ADR-009 (principal from session only)
    """

    def __init__(self, pool: "psycopg_pool.ConnectionPool") -> None:
        self._pool = pool

    def issue(self, token_hash: str, user_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id) VALUES (%s, %s)"
                " ON CONFLICT (token_hash) DO NOTHING",
                (token_hash, user_id),
            )

    def resolve(self, token_hash: str) -> str | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT user_id FROM sessions WHERE token_hash = %s", (token_hash,)
            ).fetchone()
        return str(row["user_id"]) if row else None

    def revoke(self, token_hash: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    def all_records(self) -> dict[str, str]:
        with self._pool.connection() as conn:
            rows = conn.execute("SELECT token_hash, user_id FROM sessions").fetchall()
        return {r["token_hash"]: str(r["user_id"]) for r in rows}


class PostgresVocabularyStore:
    """Owner-scoped familiarity state on PostgreSQL.

    Implements: FR-VOC-002; ADR-009 (owner-scoped); S6
    """

    def __init__(self, pool: "psycopg_pool.ConnectionPool") -> None:
        self._pool = pool

    def set_state(self, *, user_id: str, entry_id: str, state: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO user_vocabulary (user_id, entry_id, state, updated_at)"
                " VALUES (%s,%s,%s, now())"
                " ON CONFLICT (user_id, entry_id)"
                " DO UPDATE SET state = EXCLUDED.state, updated_at = now()",
                (user_id, entry_id, state),
            )

    def get_state(self, user_id: str, entry_id: str) -> str | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT state FROM user_vocabulary WHERE user_id = %s AND entry_id = %s",
                (user_id, entry_id),
            ).fetchone()
        return row["state"] if row else None

    def count_state(self, user_id: str, state: str) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT count(*) AS n FROM user_vocabulary"
                " WHERE user_id = %s AND state = %s",
                (user_id, state),
            ).fetchone()
        return int(row["n"]) if row else 0


class PostgresEventStore:
    """Append-only learning events on PostgreSQL with idempotency.

    Implements: ADR-008 (append-only, idempotent); INV-PROG-001; S6.
    Only INSERT + SELECT are issued: the app_runtime role has no UPDATE/DELETE
    on learning_events (INV-PROG-001 enforcement by grant).
    """

    def __init__(self, pool: "psycopg_pool.ConnectionPool") -> None:
        self._pool = pool

    def append(
        self,
        *,
        user_id: str,
        event_type: str,
        payload: dict,
        idempotency_key: str,
        corrects_event_id: int | None = None,
    ) -> None:
        from psycopg.types.json import Jsonb

        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO learning_events"
                " (user_id, event_type, payload, idempotency_key, corrects_event_id)"
                " VALUES (%s,%s,%s,%s,%s)"
                " ON CONFLICT (user_id, idempotency_key) DO NOTHING",
                (user_id, event_type, Jsonb(payload), idempotency_key, corrects_event_id),
            )

    def for_user(self, user_id: str) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT event_type, payload, idempotency_key FROM learning_events"
                " WHERE user_id = %s ORDER BY occurred_at",
                (user_id,),
            ).fetchall()
        return [
            {
                "user_id": user_id,
                "event_type": r["event_type"],
                "payload": r["payload"] or {},
                "idempotency_key": r["idempotency_key"],
            }
            for r in rows
        ]


class PostgresStores:
    """Container wiring the PostgreSQL repositories (production).

    Implements: ADR-009; S6; ADR-011; INV-SEC-001 (no corpus write path)
    """

    def __init__(self, pool: "psycopg_pool.ConnectionPool") -> None:
        self.users = PostgresUserRepository(pool)
        self.sessions = PostgresSessionRepository(pool)
        self.vocabulary = PostgresVocabularyStore(pool)
        self.events = PostgresEventStore(pool)
        # Chat-session ids are ephemeral per process for R1; a dedicated table
        # can replace this in a later migration without changing the API.
        self.chat_sessions = InMemoryChatSessionStore()
        self.loader = None
        self._pool = pool

    def close(self) -> None:
        """Close the connection pool on application shutdown."""
        self._pool.close()


def make_pool(database_url: str, *, min_size: int = 1, max_size: int = 5):
    """Create a psycopg connection pool for the configured DATABASE_URL.

    Implements: ADR-011 (Render managed Postgres); INV-SEC-001 (the DSN must
    be the app_runtime role). Raises if psycopg is unavailable.
    """
    if psycopg_pool is None:
        raise RuntimeError("psycopg is not installed; cannot open a database pool")
    from psycopg.rows import dict_row

    pool = psycopg_pool.ConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    pool.wait(timeout=10)
    return pool
