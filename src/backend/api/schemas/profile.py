"""ProfileSchema - authoritative language and CEFR validation at the API boundary.

Element: ProfileSchema
Implements: INV-LANG-001, INV-CEFR-001; RP-015; ADR-009
A payload with ``language != 'en'`` or a level outside A1/A2/B1/B2 is rejected
with HTTP 422 and is never persisted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.backend.contracts.models import SUPPORTED_LANGUAGE, CefrLevel

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LEN = 8


class ProfileValidationError(Exception):
    """Raised when a profile/registration payload violates the boundary.

    Implements: INV-LANG-001, INV-CEFR-001; RP-015 (HTTP 422)
    """

    status_code: int = 422

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        self.body = {field: reason}
        super().__init__(f"{field}: {reason}")


@dataclass(frozen=True)
class ValidatedRegistration:
    """Normalised registration payload that passed validation.

    Implements: FR-AUTH-001; INV-LANG-001, INV-CEFR-001
    """

    email: str
    password: str
    cefr_level: str
    language: str


@dataclass(frozen=True)
class ValidatedProfileUpdate:
    """Normalised profile-update payload that passed validation.

    Implements: FR-PROF-001; INV-CEFR-001
    """

    cefr_level: str | None
    learning_goals: str | None


class ProfileSchema:
    """Boundary validator for language, CEFR level and basic identity fields.

    Implements: INV-LANG-001, INV-CEFR-001; RP-015; ADR-009
    """

    @staticmethod
    def validate_language(language: str) -> str:
        """INV-LANG-001: only 'en' is accepted; anything else is 422."""
        if language != SUPPORTED_LANGUAGE:
            raise ProfileValidationError("language", "only 'en' is supported")
        return language

    @staticmethod
    def validate_cefr(level: str) -> str:
        """INV-CEFR-001: only A1/A2/B1/B2 are accepted; anything else is 422."""
        if level not in CefrLevel.values():
            raise ProfileValidationError("cefr_level", "must be one of A1, A2, B1, B2")
        return level

    @classmethod
    def validate_registration(
        cls,
        *,
        email: str,
        password: str,
        cefr_level: str,
        language: str,
    ) -> ValidatedRegistration:
        """Validate a registration payload.

        Implements: FR-AUTH-001; INV-LANG-001, INV-CEFR-001; RP-015
        """
        if not _EMAIL_RE.match(email):
            raise ProfileValidationError("email", "invalid email format")
        if len(password) < _MIN_PASSWORD_LEN:
            raise ProfileValidationError("password", "must be at least 8 characters")
        cls.validate_language(language)
        cls.validate_cefr(cefr_level)
        return ValidatedRegistration(
            email=email.lower(),
            password=password,
            cefr_level=cefr_level,
            language=language,
        )

    @classmethod
    def validate_update(
        cls,
        *,
        cefr_level: str | None,
        learning_goals: str | None,
    ) -> ValidatedProfileUpdate:
        """Validate a profile update; only provided fields are checked.

        Implements: FR-PROF-001; INV-CEFR-001; RP-015
        """
        if cefr_level is not None:
            cls.validate_cefr(cefr_level)
        if learning_goals is not None and len(learning_goals) > 500:
            raise ProfileValidationError("learning_goals", "must be at most 500 characters")
        return ValidatedProfileUpdate(cefr_level=cefr_level, learning_goals=learning_goals)
