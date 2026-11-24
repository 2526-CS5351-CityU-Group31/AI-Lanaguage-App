"""AuthRouter - register/login/logout and owner-scoped profile endpoints.

Element: AuthRouter
Implements: FR-AUTH-001, FR-PROF-001; INV-AUTH-001 (via AuthSecurity);
  INV-LANG-001, INV-CEFR-001 (via ProfileSchema); ADR-009; RP-015

The router decides no identity and performs no cryptography of its own: session
identity and ownership come only from ``AuthSecurity`` (the human-authored gate
module), and language/CEFR validation comes only from ``ProfileSchema``. This
module is buildable under guard (permission-model.md §2) because its
correctness depends on those two authorities, not on its own logic.
"""

from __future__ import annotations

from src.backend.api.schemas.profile import ProfileSchema
from src.backend.auth.security import (
    AuthenticationError,
    AuthorizationError,
)
from src.backend.contracts.models import Principal, Profile

__all__ = [
    "AuthRouter",
    "RegistrationConflict",
    "AuthenticationError",
    "AuthorizationError",
]


class RegistrationConflict(Exception):
    """A registration email already exists.

    Implements: FR-AUTH-001 (duplicate email -> conflict)
    """

    status_code: int = 409

    def __init__(self, reason: str = "email already registered") -> None:
        self.reason = reason
        self.body: dict[str, str] = {}
        super().__init__(reason)


class AuthRouter:
    """HTTP-facing auth service. All security is delegated to ``AuthSecurity``.

    Implements: FR-AUTH-001, FR-PROF-001; ADR-009
    """

    def __init__(self, security: object, stores: object) -> None:
        self._security = security
        self._stores = stores

    def register(
        self,
        *,
        email: str,
        password: str,
        cefr_level: str,
        language: str,
    ) -> str:
        """Validate, reject duplicates, hash the password, issue a session.

        Implements: FR-AUTH-001; INV-LANG-001, INV-CEFR-001; RP-015
        """
        payload = ProfileSchema.validate_registration(
            email=email, password=password, cefr_level=cefr_level, language=language
        )
        users = self._stores.users
        if users.get_by_email(payload.email) is not None:
            raise RegistrationConflict()

        password_hash, salt = self._security.hash_password(payload.password)
        record = self._security.create_user_record(
            email=payload.email,
            password_hash=password_hash,
            salt=salt,
            cefr_level=payload.cefr_level,
            language=payload.language,
        )
        users.add(record)
        return self._security.issue_token(record.user_id)

    def login(self, *, email: str, password: str) -> str:
        """Verify credentials and issue a session; invalid creds -> 401.

        Implements: FR-AUTH-001; RP-012 (no user-existence disclosure)
        """
        record = self._stores.users.get_by_email(email.lower())
        if record is None:
            raise AuthenticationError()
        if not self._security.verify_password(password, record.password_hash, record.salt):
            raise AuthenticationError()
        return self._security.issue_token(record.user_id)

    def logout(self, token: str) -> None:
        """Revoke the session token.

        Implements: FR-AUTH-001
        """
        self._security.revoke_token(token)

    def resolve_principal(self, token: str) -> Principal | None:
        """Return the session principal, or None for a forged/absent token.

        Implements: INV-AUTH-001 (principal from session only)
        """
        return self._security.resolve_principal(token)

    def get_profile(self, token: str) -> Profile:
        """Read the caller's own profile.

        Implements: FR-PROF-001; INV-AUTH-001
        """
        principal = self._require_principal(token)
        return self._profile_of(principal)

    def update_profile(
        self,
        token: str,
        *,
        cefr_level: str | None = None,
        learning_goals: str | None = None,
    ) -> Profile:
        """Validate and persist a profile update for the owner only.

        Implements: FR-PROF-001; INV-CEFR-001; RP-015
        """
        principal = self._require_principal(token)
        update = ProfileSchema.validate_update(
            cefr_level=cefr_level, learning_goals=learning_goals
        )
        record = self._stores.users.get_by_id(principal.user_id)
        if record is None:
            raise AuthorizationError()
        if update.cefr_level is not None:
            record.cefr_level = update.cefr_level
        if update.learning_goals is not None:
            record.learning_goals = update.learning_goals
        self._stores.users.update(record)
        return self._profile_of(principal)

    def get_profile_of(self, token: str, target_user_id: str) -> Profile:
        """Read a profile only if the session principal owns it.

        Implements: INV-AUTH-001; RP-012 (404, empty body, no mutation)
        """
        principal = self._security.require_owner(token, target_user_id)
        return self._profile_of(principal)

    def _require_principal(self, token: str) -> Principal:
        principal = self._security.resolve_principal(token)
        if principal is None:
            raise AuthenticationError("invalid session")
        return principal

    def _profile_of(self, principal: Principal) -> Profile:
        record = self._stores.users.get_by_id(principal.user_id)
        if record is None:
            raise AuthorizationError()
        return Profile(
            user_id=record.user_id,
            email=record.email,
            cefr_level=record.cefr_level,
            language=record.language,
            learning_goals=record.learning_goals,
        )
