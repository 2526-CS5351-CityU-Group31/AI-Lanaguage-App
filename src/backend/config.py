"""Configuration boundary - the only module that reads the environment.

Element: config (support package, not an architectural element)
Implements: ADR-011 (PORT key, Render topology); configuration-governance
  §1 precedence, §2 key table, §3 fail-loud, §4 frozen object; S5 (single env
  reader); NFR-COST-001 (context_token_budget default 1,500)

Any invalid configuration is fatal at startup with exit code 78 (EX_CONFIG).
No secret value is ever included in an error message.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

EXIT_CONFIG = 78

_PLACEHOLDER_SECRETS = {"changeme", "test", "xxx", "", "change-me", "password"}

_ENVIRONMENTS = {"dev", "test", "prod"}
_LLM_MODES = {"stub", "live"}


class ConfigError(Exception):
    """Fatal configuration error; carries the process exit code.

    Implements: configuration-governance §3 (fail-loud, exit 78)
    """

    exit_code: int = EXIT_CONFIG

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__(
            "FATAL config: %d invalid key(s)\n  - %s"
            % (len(self.errors), "\n  - ".join(self.errors))
        )


@dataclass(frozen=True)
class Config:
    """Frozen configuration object injected into services.

    Implements: configuration-governance §4 (immutability); ADR-011
    """

    environment: str
    database_url: str
    session_secret: str
    llm_mode: str
    embedding_model: str
    embedding_dim: int
    prompt_version: str
    port: int = 8000
    context_token_budget: int = 1500
    compaction_message_limit: int = 6
    max_ai_calls_per_day: int = 50
    rate_limit_per_minute: int = 60
    llm_api_key: str | None = None
    llm_model: str | None = None
    cors_allowed_origins: tuple[str, ...] = ()


def _get(environ: Mapping[str, str], key: str) -> str | None:
    value = environ.get(key)
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _parse_int(raw: str, key: str, low: int, high: int, errors: list[str]) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        errors.append(f"{key}: not an integer")
        return None
    if not (low <= value <= high):
        errors.append(f"{key}: out of range [{low}, {high}]")
        return None
    return value


def _is_loopback_origin(origin: str) -> bool:
    """True for a loopback dev origin: http://localhost or http://127.0.0.1, any port.

    Implements: configuration-governance §2 (CORS); allows a locally-run
    frontend to call a prod deployment without weakening external http rules.
    """
    if not origin.startswith("http://"):
        return False
    host = origin[len("http://"):].split("/", 1)[0].split(":", 1)[0].lower()
    return host in {"localhost", "127.0.0.1"}


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    """Validate the environment once and return a frozen Config.

    Implements: configuration-governance §2 (key table), §3 (fail-loud);
      ADR-011 (PORT); S5 (single env reader)

    ``environ`` is accepted for tests and defaults to ``os.environ``. The
    caller never receives a partially-valid object: all errors are collected
    and raised together, with no secret value echoed.
    """
    env = os.environ if environ is None else environ
    errors: list[str] = []

    environment = _get(env, "ENVIRONMENT")
    if environment is None:
        errors.append("ENVIRONMENT: required")
    elif environment not in _ENVIRONMENTS:
        errors.append("ENVIRONMENT: must be one of dev/test/prod")

    database_url = _get(env, "DATABASE_URL")
    if database_url is None:
        errors.append("DATABASE_URL: required")
    elif not database_url.startswith("postgresql://"):
        errors.append("DATABASE_URL: scheme must be postgresql://")

    session_secret = _get(env, "SESSION_SECRET")
    if session_secret is None:
        errors.append("SESSION_SECRET: required")
    elif len(session_secret) < 32:
        errors.append("SESSION_SECRET: must be >= 32 bytes")
    elif environment == "prod" and session_secret.lower() in _PLACEHOLDER_SECRETS:
        errors.append("SESSION_SECRET: placeholder value rejected in prod")

    llm_mode = _get(env, "LLM_MODE")
    if llm_mode is None:
        llm_mode = "live" if environment == "prod" else "stub"
    elif llm_mode not in _LLM_MODES:
        errors.append("LLM_MODE: must be stub or live")

    llm_api_key = _get(env, "LLM_API_KEY")
    if llm_mode == "live" and llm_api_key is None:
        errors.append("LLM_API_KEY: required when LLM_MODE=live")

    llm_model = _get(env, "LLM_MODEL")
    if llm_mode == "live":
        if llm_model is None:
            errors.append("LLM_MODEL: required when LLM_MODE=live")
        elif llm_model in {"latest", "*"}:
            errors.append("LLM_MODEL: must be a pinned id")

    embedding_model = _get(env, "EMBEDDING_MODEL")
    if embedding_model is None:
        errors.append("EMBEDDING_MODEL: required")

    embedding_dim = None
    raw_dim = _get(env, "EMBEDDING_DIM")
    if raw_dim is None:
        errors.append("EMBEDDING_DIM: required")
    else:
        embedding_dim = _parse_int(raw_dim, "EMBEDDING_DIM", 1, 4096, errors)

    prompt_version = _get(env, "PROMPT_VERSION") or "prompt_v1.0.0"
    if not prompt_version.startswith("prompt_v"):
        errors.append("PROMPT_VERSION: must match prompt_vX.Y.Z")

    port = 8000
    raw_port = _get(env, "PORT")
    if raw_port is not None:
        parsed_port = _parse_int(raw_port, "PORT", 1, 65535, errors)
        if parsed_port is not None:
            port = parsed_port

    budget = 1500
    raw_budget = _get(env, "CONTEXT_TOKEN_BUDGET")
    if raw_budget is not None:
        parsed_budget = _parse_int(raw_budget, "CONTEXT_TOKEN_BUDGET", 1000, 4000, errors)
        if parsed_budget is not None:
            budget = parsed_budget

    compaction = 6
    raw_compaction = _get(env, "COMPACTION_MESSAGE_LIMIT")
    if raw_compaction is not None:
        parsed_compaction = _parse_int(raw_compaction, "COMPACTION_MESSAGE_LIMIT", 4, 20, errors)
        if parsed_compaction is not None:
            compaction = parsed_compaction

    max_calls = 50
    raw_calls = _get(env, "MAX_AI_CALLS_PER_DAY")
    if raw_calls is not None:
        parsed_calls = _parse_int(raw_calls, "MAX_AI_CALLS_PER_DAY", 1, 1000, errors)
        if parsed_calls is not None:
            max_calls = parsed_calls

    rate_limit = 60
    raw_rate = _get(env, "RATE_LIMIT_PER_MINUTE")
    if raw_rate is not None:
        parsed_rate = _parse_int(raw_rate, "RATE_LIMIT_PER_MINUTE", 1, 600, errors)
        if parsed_rate is not None:
            rate_limit = parsed_rate

    # CORS_ALLOWED_ORIGINS: comma list. In prod, entries must be exact https
    # origins, EXCEPT loopback dev origins (http://localhost / http://127.0.0.1,
    # any port) which are allowed so a locally-run frontend can call prod.
    origins: list[str] = []
    raw_cors = _get(env, "CORS_ALLOWED_ORIGINS")
    if raw_cors:
        for origin in raw_cors.split(","):
            origin = origin.strip()
            if not origin:
                continue
            if origin == "*":
                errors.append("CORS_ALLOWED_ORIGINS: wildcard not allowed")
            elif environment == "prod" and not origin.startswith("https://") and not _is_loopback_origin(origin):
                errors.append(
                    "CORS_ALLOWED_ORIGINS: prod origins must be https or loopback"
                )
            else:
                origins.append(origin)

    if errors:
        raise ConfigError(errors)

    return Config(
        environment=environment,
        database_url=database_url,
        session_secret=session_secret,
        llm_mode=llm_mode,
        embedding_model=embedding_model,
        embedding_dim=embedding_dim,
        prompt_version=prompt_version,
        port=port,
        context_token_budget=budget,
        compaction_message_limit=compaction,
        max_ai_calls_per_day=max_calls,
        rate_limit_per_minute=rate_limit,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        cors_allowed_origins=tuple(origins),
    )


# ---------------------------------------------------------------------------
# Provider gateway configuration (model gateway seam, from ai/rag-runtime merge)
# Implements: S5 (single env reader); ADR-001, ADR-005, ADR-006; FR-CHAT-001
# ---------------------------------------------------------------------------

CITYU_BASE_URL = "https://llm.cs.cityu.edu.hk/v1"
CITYU_CHAT_MODEL = "CS5351/DeepSeek-V4-Flash"
LLM_API_KEY_ENV_VAR = "LLM_API_KEY"


@dataclass(frozen=True)
class ProviderGatewayConfig:
    """S5 / configuration-governance §2-§4: frozen provider gateway configuration.

    ``api_key`` is excluded from ``repr`` so an accidental log or traceback
    cannot disclose it. No validation error includes a secret value.
    """

    api_key: str = field(repr=False)
    base_url: str = CITYU_BASE_URL
    chat_model: str = CITYU_CHAT_MODEL

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("api_key must be non-empty")
        if not self.base_url.strip():
            raise ValueError("base_url must be non-empty")
        if not self.base_url.startswith("https://"):
            raise ValueError("base_url must use https")
        if not self.chat_model.strip():
            raise ValueError("chat_model must be non-empty")


def load_provider_gateway_config() -> ProviderGatewayConfig:
    """Read ``LLM_API_KEY`` once at the composition edge and freeze the config.

    Implements: S5 / configuration-governance §2-§5; ADR-001 §Decision.
    Raises ``RuntimeError`` naming the environment variable, never its value.
    """
    api_key = os.environ.get(LLM_API_KEY_ENV_VAR, "").strip()
    if not api_key:
        raise RuntimeError(
            f"{LLM_API_KEY_ENV_VAR} is required for the CityU provider gateway"
        )
    return ProviderGatewayConfig(api_key=api_key)
