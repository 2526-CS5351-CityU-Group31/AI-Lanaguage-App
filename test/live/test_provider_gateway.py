"""Guarded live smoke test for the CityU provider gateway.

Implements: ADR-005 §Decision; ADR-006 §Decision; FR-CHAT-001,
NFR-PERF-001 (partial: bounded timeout only), NFR-COST-001 (partial: usage
recording only).

The test is skipped unless ``LLM_API_KEY`` is available through the approved
config factory. It makes one structured request and never prints the prompt,
completion, or key. It is a developer smoke test, not the NFR-PERF-001 or
NFR-COST-001 release gate.
"""

from __future__ import annotations

import json

import pytest

from backend.ai_companion.provider_gateway import (
    CityUModelGateway,
    UrllibHttpTransport,
)
from backend.config import load_provider_gateway_config
from backend.contracts.ai_companion import ModelRequest


@pytest.fixture(scope="module")
def live_gateway() -> CityUModelGateway:
    try:
        config = load_provider_gateway_config()
    except RuntimeError:
        pytest.skip("LLM_API_KEY is not configured; live provider test skipped")
    return CityUModelGateway(config, UrllibHttpTransport())


def test_provider_gateway_structured_output_live(
    live_gateway: CityUModelGateway,
) -> None:
    """ADR-005/ADR-006, FR-CHAT-001: one real structured request returns JSON and usage."""
    response = live_gateway.complete(
        ModelRequest(
            request_id="req-live-provider-1",
            prompt=(
                "Return exactly one JSON object with a single key "
                '"ok" whose value is true.'
            ),
            task="conversation",
            schema_id="conversation.v1",
            timeout_ms=30000,
            max_output_tokens=64,
            temperature=0.0,
        )
    )

    assert isinstance(response.text, str)
    assert response.text.strip()
    payload = json.loads(response.text)
    assert isinstance(payload, dict)
    assert payload
    assert response.model_id.strip()
    assert response.prompt_tokens >= 0
    assert response.completion_tokens >= 0
