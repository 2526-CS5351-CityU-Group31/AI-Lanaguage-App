"""Configuration boundary for the provider-backed model gateway.

Element: configuration support for the Tutor / ModelGateway seam.
Implements: S5 (single environment reader) and configuration-governance
§2-§5; ADR-001 §Decision, ADR-005 §Decision, ADR-006 §Decision, FR-CHAT-001.

Only this module may read the environment. The gateway receives a frozen
``ProviderGatewayConfig`` by dependency injection and never reads ``os.environ``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

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
