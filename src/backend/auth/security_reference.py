"""AuthSecurity reference adapter - a stdlib-only implementation of the
``AuthSecurity`` interface for dev/offline wiring.

Element: AuthSecurity (reference adapter, NOT the gate module)
Implements: ADR-009; INV-AUTH-001; FR-AUTH-001

================================================================================
This is a REFERENCE implementation provided so the module can run in dev and
offline without touching the human-authored gate file ``security.py``. It is
NOT the production authority: the human author owns ``security.py`` and may
replace this adapter. Two reviewers must still sign off before production use.
================================================================================
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

from src.backend.auth.security import (
    AuthenticationError,
    AuthSecurity,
    AuthorizationError,
)
from src.backend.contracts.models import Principal, UserRecord

_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16


def _hash_token(token: str) -> str:
    """Hash a session token so only the digest is stored.

    Implements: FR-AUTH-001; ADR-009
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ReferenceAuthSecurity(AuthSecurity):
    """Stdlib-only implementation of the AuthSecurity contract.

    Implements: ADR-009; INV-AUTH-001; FR-AUTH-001
    """

    def __init__(self, stores: object) -> None:
        self._stores = stores

    def hash_password(self, password: str) -> tuple[str, str]:
        """Derive a scrypt hash and a random salt.

        Implements: FR-AUTH-001 (no plaintext storage)
        """
        salt = secrets.token_bytes(_SALT_BYTES).hex()
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=32,
        )
        return digest.hex(), salt

    def verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """Constant-time password verification.

        Implements: FR-AUTH-001
        """
        if not password_hash or not salt:
            return False
        try:
            candidate = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt),
                n=_SCRYPT_N,
                r=_SCRYPT_R,
                p=_SCRYPT_P,
                dklen=32,
            ).hex()
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(candidate, password_hash)

    def create_user_record(
        self,
        *,
        email: str,
        password_hash: str,
        salt: str,
        cefr_level: str,
        language: str,
    ) -> UserRecord:
        """Build a UserRecord with a server-generated user id.

        Implements: FR-AUTH-001; ADR-009 (identity is server-generated)
        """
        return UserRecord(
            user_id=str(uuid.uuid4()),
            email=email,
            password_hash=password_hash,
            salt=salt,
            cefr_level=cefr_level,
            language=language,
        )

    def issue_token(self, user_id: str) -> str:
        """Issue a random token and store only its hash.

        Implements: FR-AUTH-001
        """
        token = secrets.token_urlsafe(32)
        self._stores.sessions.issue(_hash_token(token), user_id)
        return token

    def resolve_principal(self, token: str) -> Principal | None:
        """Resolve a token to its principal via the session store only.

        Implements: INV-AUTH-001 (principal from session only)
        """
        if not token:
            return None
        user_id = self._stores.sessions.resolve(_hash_token(token))
        if user_id is None:
            return None
        record = self._stores.users.get_by_id(user_id)
        if record is None:
            return None
        return Principal(user_id=record.user_id, email=record.email)

    def revoke_token(self, token: str) -> None:
        """Revoke a session token.

        Implements: FR-AUTH-001
        """
        self._stores.sessions.revoke(_hash_token(token))

    def require_owner(self, token: str, target_user_id: str) -> Principal:
        """Authorise access; 404 with empty body unless the principal owns it.

        Implements: INV-AUTH-001; RP-012 (no disclosure, no mutation)
        """
        principal = self.resolve_principal(token)
        if principal is None or principal.user_id != target_user_id:
            raise AuthorizationError()
        return principal
