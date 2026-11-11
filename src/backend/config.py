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
from dataclasses import dataclass
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
    llm_api_key: str | None = None
    llm_model: str | None = None


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
        llm_api_key=llm_api_key,
        llm_model=llm_model,
    )
