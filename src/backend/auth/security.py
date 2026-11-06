"""AuthSecurity - authoritative session identity and per-record authorization.

================================================================================
HUMAN-AUTHORED GATE MODULE (permission-model.md §2; role-ownership.md).
The Build agent has NO access to this file. The interface, error types and
docstrings below are a scaffold written for a human author to implement.
Do not ship until a human author + ADR-009 reference + a 20-probe negative
suite + two reviewers have signed off (.agent/rules.md §4).
================================================================================

Element: AuthSecurity
Implements: ADR-009; INV-AUTH-001
Enforces:
  - The principal is derived ONLY from the authenticated session; no request
    payload may set a user_id (INV-AUTH-001).
  - Every record query is scoped to the authenticated user id; a foreign id
    yields HTTP 404 with an empty body and zero state mutation (INV-AUTH-001,
    RP-012).
  - Passwords are hashed with a memory-hard KDF and never stored in plaintext;
    tokens are random and stored only as a hash.
"""

from __future__ import annotations


class AuthenticationError(Exception):
    """Bad credentials or an absent/invalid session.

    Implements: FR-AUTH-001; RP-012
    """

    status_code: int = 401

    def __init__(self, reason: str = "invalid credentials") -> None:
        self.reason = reason
        self.body: dict[str, str] = {}
        super().__init__(reason)


class AuthorizationError(Exception):
    """A request for a record the principal does not own, or an unknown owner.

    Implements: INV-AUTH-001; ADR-009 fallback (404, empty body, no mutation)
    """

    status_code: int = 404

    def __init__(self, reason: str = "not found") -> None:
        self.reason = reason
        self.body: dict[str, str] = {}
        super().__init__(reason)


class AuthSecurity:
    """Session identity and per-record authorization.

    Implements: ADR-009; INV-AUTH-001

    The concrete implementation must:
      1. ``hash_password`` / ``verify_password`` using ``hashlib.scrypt`` with a
         per-user random salt (stdlib only; no new dependency).
      2. ``issue_token`` a ``secrets.token_urlsafe(32)`` token, store only its
         SHA-256 hash via ``SessionRepository.issue``.
      3. ``resolve_principal`` map a token to a ``Principal`` from the session
         store only; a forged/absent token returns ``None``.
      4. ``require_owner`` raise ``AuthorizationError`` (404) unless the target
         user id equals the principal's ``user_id``; it must never mutate state
         on the failure path.
    """

    def __init__(self, stores: object) -> None:
        raise NotImplementedError(
            "AuthSecurity is a human-authored gate module; see module docstring."
        )

    def hash_password(self, password: str) -> tuple[str, str]:
        """Return ``(password_hash, salt)`` using a memory-hard KDF.

        Implements: FR-AUTH-001 (no plaintext storage)
        """
        raise NotImplementedError

    def create_user_record(
        self,
        *,
        email: str,
        password_hash: str,
        salt: str,
        cefr_level: str,
        language: str,
    ) -> "object":
        """Construct a new ``UserRecord`` with a server-generated user_id.

        Implements: FR-AUTH-001; ADR-009 (users written by AuthSecurity)
        """
        raise NotImplementedError

    def verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """Constant-time verification of a password against a stored hash.

        Implements: FR-AUTH-001
        """
        raise NotImplementedError

    def issue_token(self, user_id: str) -> str:
        """Issue a random session token and store only its hash.

        Implements: FR-AUTH-001; ADR-009
        """
        raise NotImplementedError

    def resolve_principal(self, token: str) -> "object | None":
        """Resolve a token to a Principal from the session store only.

        Implements: INV-AUTH-001 (principal from session only)
        """
        raise NotImplementedError

    def revoke_token(self, token: str) -> None:
        """Revoke a session token (logout).

        Implements: FR-AUTH-001
        """
        raise NotImplementedError

    def require_owner(self, token: str, target_user_id: str) -> "object":
        """Authorise a record access; 404 with empty body if not the owner.

        Implements: INV-AUTH-001; RP-012 (no disclosure, no mutation)
        """
        raise NotImplementedError
