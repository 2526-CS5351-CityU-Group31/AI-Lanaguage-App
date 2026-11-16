"""Offline contract tests for the CityU ModelGateway adapter.

Covers ADR-001, ADR-005, ADR-006, FR-CHAT-001, NFR-COST-001 (partial),
NFR-PERF-001 (partial), INV-CITE-001 (support), and S5.

Every provider call in this module goes through an injected fake transport or a
monkeypatched ``urllib.request.urlopen``. No test opens a socket.
"""

from __future__ import annotations

import ast
import json
import logging
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from backend.ai_companion.prompt_assembly import PromptAssembler
from backend.ai_companion.provider_gateway import (
    CityUModelGateway,
    HttpTransport,
    ProviderHttpRequest,
    ProviderHttpResponse,
    UrllibHttpTransport,
)
from backend.ai_companion.rag_pipeline import RagPipeline, RagRequest
from backend.ai_companion.retrieval_adapter import RetrievalAdapter
from backend.ai_companion.tutor import Tutor, TutorConfig, TutorRequest
from backend.config import ProviderGatewayConfig, load_provider_gateway_config
from backend.contracts.ai_companion import (
    INSUFFICIENT_EVIDENCE_PHRASE,
    InvalidRequestError,
    ModelGatewayError,
    ModelPermanentError,
    ModelRateLimitError,
    ModelRequest,
    ModelResponse,
    ModelTimeoutError,
    TutorUnavailableError,
)
from backend.safety_boundary.citation_validator import CitationValidator

from fakes import FakeRetrievalService, make_chunk

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_FILE = REPO_ROOT / "src/backend/config.py"
PROVIDER_FILE = REPO_ROOT / "src/backend/ai_companion/provider_gateway.py"

FAKE_KEY = "FAKE-KEY-MARKER-123"
PROMPT_MARKER = "PROMPT-MARKER: teach the past tense."
COMPLETION_MARKER = "COMPLETION-MARKER: Use the past tense."
BODY_MARKER = "BODY-MARKER: provider-only metadata"

CITYU_BASE_URL = "https://llm.cs.cityu.edu.hk/v1"
CHAT_COMPLETIONS_URL = f"{CITYU_BASE_URL}/chat/completions"
CHAT_MODEL = "CS5351/DeepSeek-V4-Flash"


def make_config(
    *,
    api_key: str = FAKE_KEY,
    base_url: str = CITYU_BASE_URL,
    chat_model: str = CHAT_MODEL,
) -> ProviderGatewayConfig:
    return ProviderGatewayConfig(
        api_key=api_key,
        base_url=base_url,
        chat_model=chat_model,
    )


def make_gateway(
    transport: HttpTransport,
    *,
    api_key: str = FAKE_KEY,
) -> CityUModelGateway:
    return CityUModelGateway(make_config(api_key=api_key), transport)


@dataclass
class FakeHttpTransport:
    """Transport stub returning canned responses or raising queued errors."""

    responses: list[ProviderHttpResponse | Exception] = field(default_factory=list)
    requests: list[ProviderHttpRequest] = field(default_factory=list)

    def post(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("FakeHttpTransport received an unexpected call")
        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


def provider_body(
    content: object = COMPLETION_MARKER,
    *,
    model: object = CHAT_MODEL,
    usage: object = None,
    extra: dict[str, object] | None = None,
) -> bytes:
    payload: dict[str, object] = {
        "id": "chatcmpl-offline-test",
        "object": "chat.completion",
        "created": 0,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "provider_note": BODY_MARKER,
    }
    if model is not None:
        payload["model"] = model
    if usage is not None:
        payload["usage"] = usage
    if extra is not None:
        payload.update(extra)
    return json.dumps(payload).encode("utf-8")


def make_request(**overrides: Any) -> ModelRequest:
    values: dict[str, Any] = {
        "request_id": "req-provider-1",
        "prompt": PROMPT_MARKER,
        "task": "conversation",
        "schema_id": "conversation.v1",
        "timeout_ms": 1234,
        "max_output_tokens": 321,
        "temperature": 0.2,
    }
    values.update(overrides)
    return ModelRequest(**values)


def make_tutor_request(**overrides: Any) -> TutorRequest:
    values: dict[str, Any] = {
        "request_id": "req-provider-tutor",
        "prompt": PROMPT_MARKER,
        "task": "conversation",
        "schema_id": "conversation.v1",
        "temperature": 0.0,
    }
    values.update(overrides)
    return TutorRequest(**values)


def make_rag_request(**overrides: Any) -> RagRequest:
    values: dict[str, Any] = {
        "request_id": "req-provider-rag",
        "task": "lesson_help",
        "prompt_version": "prompt_v1.0.0",
        "learner_profile": "English, level A1.",
        "resumable_state": "stage=practice.",
        "history": (),
        "current_turn": "Explain the past tense.",
        "requires_grounding": True,
        "query": "past tense",
        "language": "en",
        "level": "A1",
        "topic": "grammar",
        "top_k": 5,
    }
    values.update(overrides)
    return RagRequest(**values)


def lesson_payload(**overrides: Any) -> str:
    values: dict[str, Any] = {
        "task": "lesson_help",
        "abstained": False,
        "source_ids": ["c1"],
        "answer": "Use the past tense for completed actions.",
    }
    values.update(overrides)
    return json.dumps(values)


def make_http_request(
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b'{"model": "test"}',
    timeout_seconds: float = 1.5,
) -> ProviderHttpRequest:
    return ProviderHttpRequest(
        url=CHAT_COMPLETIONS_URL,
        headers=headers
        if headers is not None
        else {
            "Authorization": f"Bearer {FAKE_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        body=body,
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# Request construction and success mapping
# ---------------------------------------------------------------------------


def test_request_shape_matches_cityu_openai_contract() -> None:
    """ADR-005/ADR-006, FR-CHAT-001: the wire request is the bounded contract."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=200, body=provider_body())]
    )
    gateway = make_gateway(transport)
    prompt = 'PROMPT-MARKER: line one\nline two "quoted" 你好'

    gateway.complete(make_request(prompt=prompt))

    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.url == CHAT_COMPLETIONS_URL
    assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Accept"] == "application/json"
    assert request.timeout_seconds == pytest.approx(1.234)

    payload = json.loads(request.body)
    assert payload == {
        "model": CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 321,
        "response_format": {"type": "json_object"},
    }
    assert "tools" not in payload
    assert "functions" not in payload
    assert "tool_choice" not in payload
    assert "request_id" not in payload
    assert "schema_id" not in payload
    assert "stream" not in payload


def test_prompt_is_sent_verbatim_as_user_content() -> None:
    """ADR-006: the assembled prompt is not modified before the provider call."""
    prompt = "\n  Keep  spacing\tand 你好.\n"
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=200, body=provider_body())]
    )

    make_gateway(transport).complete(make_request(prompt=prompt))

    payload = json.loads(transport.requests[0].body)
    assert payload["messages"] == [{"role": "user", "content": prompt}]


def test_success_maps_text_model_and_usage() -> None:
    """ADR-006 / FR-CHAT-001: provider text, model id, and usage are mapped."""
    transport = FakeHttpTransport(
        responses=[
            ProviderHttpResponse(
                status_code=200,
                body=provider_body(
                    COMPLETION_MARKER,
                    model="CS5351/DeepSeek-V4-Flash-2026-01",
                    usage={"prompt_tokens": 17, "completion_tokens": 9},
                ),
            )
        ]
    )

    result = make_gateway(transport).complete(make_request())

    assert isinstance(result, ModelResponse)
    assert result.text == COMPLETION_MARKER
    assert result.model_id == "CS5351/DeepSeek-V4-Flash-2026-01"
    assert result.prompt_tokens == 17
    assert result.completion_tokens == 9


def test_provider_text_is_returned_unchanged() -> None:
    """ADR-005, INV-CITE-001 (support): the gateway never strips or repairs JSON."""
    content = '\n  ```json\n{"answer": "ok"}\n```  \n'
    transport = FakeHttpTransport(
        responses=[
            ProviderHttpResponse(
                status_code=200,
                body=provider_body(content),
            )
        ]
    )

    result = make_gateway(transport).complete(make_request())

    assert result.text == content


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"prompt_tokens": 10},
        {"prompt_tokens": "10", "completion_tokens": 5},
        {"prompt_tokens": True, "completion_tokens": 5},
        {"prompt_tokens": -1, "completion_tokens": -1},
    ],
)
def test_missing_usage_reports_zero_and_records_omission(
    usage: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-006 / NFR-COST-001 (partial): omitted usage is zero and recorded, not estimated."""
    caplog.set_level(logging.INFO, logger="backend.ai_companion.provider_gateway")
    transport = FakeHttpTransport(
        responses=[
            ProviderHttpResponse(
                status_code=200,
                body=provider_body(usage=usage),
            )
        ]
    )

    result = make_gateway(transport).complete(make_request())

    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0
    assert "usage_present=False" in caplog.text


@pytest.mark.parametrize("model", [None, "", "   ", 123])
def test_provider_model_id_falls_back_to_configured_model(model: object) -> None:
    """ADR-006: an absent or invalid provider model id falls back to the configured model."""
    transport = FakeHttpTransport(
        responses=[
            ProviderHttpResponse(
                status_code=200,
                body=provider_body(model=model),
            )
        ]
    )

    result = make_gateway(transport).complete(make_request())

    assert result.model_id == CHAT_MODEL


@pytest.mark.parametrize(
    "overrides",
    [
        {"prompt": "   "},
        {"timeout_ms": 0},
        {"timeout_ms": -1},
        {"max_output_tokens": 0},
        {"temperature": 1.5},
    ],
)
def test_invalid_request_never_reaches_transport(
    overrides: dict[str, Any],
) -> None:
    """ADR-005 / FR-CHAT-001: invalid input fails before any provider call."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=200, body=provider_body())]
    )

    with pytest.raises(InvalidRequestError):
        make_gateway(transport).complete(make_request(**overrides))

    assert transport.requests == []


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [408, 504])
def test_http_408_and_504_map_to_timeout(status_code: int) -> None:
    """RP-004: provider timeout statuses map to a retryable timeout error."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=status_code, body=b"")]
    )

    with pytest.raises(ModelTimeoutError) as excinfo:
        make_gateway(transport).complete(make_request())

    assert excinfo.value.retryable is True


def test_socket_timeout_maps_to_timeout() -> None:
    """RP-004: a socket/read timeout maps to ModelTimeoutError."""
    transport = FakeHttpTransport(responses=[TimeoutError("read timed out")])

    with pytest.raises(ModelTimeoutError) as excinfo:
        make_gateway(transport).complete(make_request())

    assert excinfo.value.retryable is True


def test_http_429_maps_to_retryable_rate_limit() -> None:
    """RP-009: HTTP 429 maps to a retryable ModelRateLimitError."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=429, body=b"")]
    )

    with pytest.raises(ModelRateLimitError) as excinfo:
        make_gateway(transport).complete(make_request())

    assert excinfo.value.retryable is True


@pytest.mark.parametrize("status_code", [500, 502])
def test_http_5xx_maps_to_retryable_gateway_error(status_code: int) -> None:
    """RP-004: provider 5xx maps to a retryable ModelGatewayError."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=status_code, body=b"")]
    )

    with pytest.raises(ModelGatewayError) as excinfo:
        make_gateway(transport).complete(make_request())

    assert type(excinfo.value) is ModelGatewayError
    assert excinfo.value.retryable is True


def test_connection_failure_maps_to_retryable_gateway_error() -> None:
    """RP-004: DNS/connection failure maps to a retryable ModelGatewayError."""
    transport = FakeHttpTransport(
        responses=[ConnectionError("connection refused")]
    )

    with pytest.raises(ModelGatewayError) as excinfo:
        make_gateway(transport).complete(make_request())

    assert type(excinfo.value) is ModelGatewayError
    assert excinfo.value.retryable is True


@pytest.mark.parametrize("status_code", [400, 401, 403])
def test_http_4xx_maps_to_permanent_error(status_code: int) -> None:
    """RP-004: non-retryable 4xx responses map to ModelPermanentError."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=status_code, body=b"")]
    )

    with pytest.raises(ModelPermanentError) as excinfo:
        make_gateway(transport).complete(make_request())

    assert type(excinfo.value) is ModelPermanentError
    assert excinfo.value.retryable is False


@pytest.mark.parametrize("body", [b"\xff\xfe", b"{not-json"])
def test_malformed_json_maps_to_permanent_error(body: bytes) -> None:
    """ADR-005: invalid provider JSON is permanent; the gateway never repairs it."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=200, body=body)]
    )

    with pytest.raises(ModelPermanentError):
        make_gateway(transport).complete(make_request())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": ["not-a-mapping"]},
        {"choices": [{}]},
        {"choices": [{"message": "not-a-mapping"}]},
    ],
)
def test_missing_or_invalid_choices_map_to_permanent_error(
    payload: object,
) -> None:
    """ADR-005: missing choices[0].message maps to ModelPermanentError."""
    body = json.dumps(payload).encode("utf-8")
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=200, body=body)]
    )

    with pytest.raises(ModelPermanentError):
        make_gateway(transport).complete(make_request())


@pytest.mark.parametrize("content", ["", "   ", 123, None, ["x"]])
def test_empty_or_non_string_content_maps_to_permanent_error(
    content: object,
) -> None:
    """ADR-005: empty or non-string content maps to ModelPermanentError."""
    transport = FakeHttpTransport(
        responses=[
            ProviderHttpResponse(
                status_code=200,
                body=provider_body(content),
            )
        ]
    )

    with pytest.raises(ModelPermanentError):
        make_gateway(transport).complete(make_request())


# ---------------------------------------------------------------------------
# Retry authority
# ---------------------------------------------------------------------------


def test_gateway_makes_exactly_one_transport_attempt() -> None:
    """RP-004: the gateway makes one attempt; Tutor owns retries."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=500, body=b"")]
    )

    with pytest.raises(ModelGatewayError):
        make_gateway(transport).complete(make_request())

    assert len(transport.requests) == 1


def test_tutor_retries_retryable_gateway_errors_up_to_three_total_attempts() -> None:
    """NFR-PERF-001 (partial) / RP-004: total attempts never exceed three."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=500, body=b"") for _ in range(3)]
    )
    tutor = Tutor(make_gateway(transport), TutorConfig(max_attempts=3))

    with pytest.raises(TutorUnavailableError):
        tutor.generate(make_tutor_request())

    assert len(transport.requests) == 3


def test_tutor_recovers_from_one_retryable_error() -> None:
    """RP-004: a retryable failure can recover within the existing bound."""
    transport = FakeHttpTransport(
        responses=[
            ProviderHttpResponse(status_code=429, body=b""),
            ProviderHttpResponse(status_code=200, body=provider_body("recovered")),
        ]
    )
    tutor = Tutor(make_gateway(transport), TutorConfig(max_attempts=3))

    result = tutor.generate(make_tutor_request())

    assert result.text == "recovered"
    assert result.attempts == 2
    assert len(transport.requests) == 2


def test_tutor_does_not_retry_permanent_error() -> None:
    """RP-004: a permanent provider failure stops after one attempt."""
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=401, body=b"")]
    )
    tutor = Tutor(make_gateway(transport), TutorConfig(max_attempts=3))

    with pytest.raises(TutorUnavailableError):
        tutor.generate(make_tutor_request())

    assert len(transport.requests) == 1


# ---------------------------------------------------------------------------
# Integration and authority boundary
# ---------------------------------------------------------------------------


def test_lesson_help_response_passes_existing_validator_and_pipeline() -> None:
    """FR-RAG-001 / INV-CITE-001: validated provider output reaches the learner."""
    transport = FakeHttpTransport(
        responses=[
            ProviderHttpResponse(
                status_code=200,
                body=provider_body(lesson_payload()),
            )
        ]
    )
    retrieval = FakeRetrievalService(chunks=(make_chunk("c1"),))
    pipeline = RagPipeline(
        retrieval=RetrievalAdapter(retrieval),
        assembler=PromptAssembler(),
        tutor=Tutor(make_gateway(transport)),
        validator=CitationValidator(),
    )

    result = pipeline.handle(make_rag_request())

    assert result.status == "accepted"
    assert result.text == "Use the past tense for completed actions."
    assert result.evidence_ids == ("c1",)
    assert result.tutor is not None
    assert result.tutor.model_id == CHAT_MODEL
    assert result.tutor.attempts == 1
    assert result.prompt_tokens <= 1500
    assert len(retrieval.calls) == 1


def test_pipeline_blocks_unvalidated_provider_citation() -> None:
    """INV-CITE-001 / NFR-QUAL-003 (partial): an invented citation never reaches the learner."""
    transport = FakeHttpTransport(
        responses=[
            ProviderHttpResponse(
                status_code=200,
                body=provider_body(lesson_payload(source_ids=["invented-source"])),
            )
        ]
    )
    pipeline = RagPipeline(
        retrieval=RetrievalAdapter(
            FakeRetrievalService(chunks=(make_chunk("c1"),))
        ),
        assembler=PromptAssembler(),
        tutor=Tutor(make_gateway(transport)),
        validator=CitationValidator(),
    )

    result = pipeline.handle(make_rag_request())

    assert result.status == "abstained"
    assert result.text == INSUFFICIENT_EVIDENCE_PHRASE
    assert "invented-source" not in result.text
    assert result.response is None


# ---------------------------------------------------------------------------
# Logging, secret handling, and offline boundaries
# ---------------------------------------------------------------------------


def test_no_secret_prompt_completion_or_body_in_logs_or_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """NFR-SEC-001 (support) / S5: logs and exceptions never contain secrets or provider content."""
    caplog.set_level(logging.DEBUG)
    config = make_config()
    assert FAKE_KEY not in repr(config)

    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=200, body=provider_body())]
    )
    result = CityUModelGateway(config, transport).complete(make_request())
    assert result.text == COMPLETION_MARKER
    assert FAKE_KEY not in repr(transport.requests[0])
    assert PROMPT_MARKER not in repr(transport.requests[0])
    for marker in (FAKE_KEY, PROMPT_MARKER, COMPLETION_MARKER, BODY_MARKER):
        assert marker not in caplog.text

    caplog.clear()
    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=500, body=provider_body())]
    )
    with pytest.raises(ModelGatewayError) as excinfo:
        CityUModelGateway(config, transport).complete(make_request())
    for marker in (FAKE_KEY, PROMPT_MARKER, COMPLETION_MARKER, BODY_MARKER):
        assert marker not in str(excinfo.value)
        assert marker not in caplog.text

    caplog.clear()
    transport = FakeHttpTransport(
        responses=[
            ProviderHttpResponse(
                status_code=200,
                body=b'{"provider_note": "BODY-MARKER"',
            )
        ]
    )
    with pytest.raises(ModelPermanentError) as excinfo:
        CityUModelGateway(config, transport).complete(make_request())
    for marker in (FAKE_KEY, PROMPT_MARKER, COMPLETION_MARKER, BODY_MARKER):
        assert marker not in str(excinfo.value)
        assert marker not in caplog.text


def test_offline_gateway_path_opens_no_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-001: the offline gateway path performs no network access."""
    def fail_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted by the provider gateway")

    monkeypatch.setattr(socket.socket, "connect", fail_connect)
    monkeypatch.setattr(socket, "create_connection", fail_connect)

    transport = FakeHttpTransport(
        responses=[ProviderHttpResponse(status_code=200, body=provider_body())]
    )

    result = make_gateway(transport).complete(make_request())

    assert result.text == COMPLETION_MARKER


# ---------------------------------------------------------------------------
# Real urllib transport, still offline
# ---------------------------------------------------------------------------


class _FakeUrlopenResponse:
    def __init__(self, status_code: int, body: bytes) -> None:
        self._status_code = status_code
        self._body = body

    def __enter__(self) -> _FakeUrlopenResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self._status_code

    def read(self) -> bytes:
        return self._body


def test_urllib_transport_passes_request_and_timeout_to_urlopen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RP-004: the stdlib transport passes the exact request and bounded timeout."""
    captured: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float | None = None,
        **kwargs: object,
    ) -> _FakeUrlopenResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeUrlopenResponse(200, b"{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    request = make_http_request()

    response = UrllibHttpTransport().post(request)

    assert response.status_code == 200
    assert response.body == b"{}"
    sent = captured["request"]
    assert isinstance(sent, urllib.request.Request)
    assert sent.full_url == CHAT_COMPLETIONS_URL
    assert sent.get_method() == "POST"
    assert sent.data == request.body
    assert captured["timeout"] == pytest.approx(1.5)
    assert sent.get_header("Authorization") == f"Bearer {FAKE_KEY}"
    assert sent.get_header("Content-type") == "application/json"
    assert sent.get_header("Accept") == "application/json"


class _NoReadBody:
    def read(self, *args: object) -> bytes:
        raise AssertionError("provider error body must not be read")

    def close(self) -> None:
        return None


def test_urllib_transport_does_not_read_http_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RP-004 / NFR-SEC-001 (support): HTTP error bodies are never read or exposed."""
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float | None = None,
        **kwargs: object,
    ) -> _FakeUrlopenResponse:
        raise urllib.error.HTTPError(
            CHAT_COMPLETIONS_URL,
            429,
            "Too Many Requests",
            None,
            _NoReadBody(),  # type: ignore[arg-type]
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    response = UrllibHttpTransport().post(make_http_request())

    assert response.status_code == 429
    assert response.body == b""


@pytest.mark.parametrize(
    "raised",
    [
        TimeoutError("timed out"),
        urllib.error.URLError(TimeoutError("timed out")),
    ],
)
def test_urllib_transport_maps_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    raised: Exception,
) -> None:
    """RP-004: transport timeouts surface as TimeoutError for the gateway to map."""
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float | None = None,
        **kwargs: object,
    ) -> _FakeUrlopenResponse:
        raise raised

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(TimeoutError):
        UrllibHttpTransport().post(make_http_request())


def test_urllib_transport_maps_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RP-004: connection/DNS failures surface as OSError for the gateway to map."""
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float | None = None,
        **kwargs: object,
    ) -> _FakeUrlopenResponse:
        raise urllib.error.URLError(ConnectionRefusedError("connection refused"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(OSError):
        UrllibHttpTransport().post(make_http_request())


# ---------------------------------------------------------------------------
# Configuration and structural boundaries
# ---------------------------------------------------------------------------


def test_config_factory_reads_key_and_repr_hides_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S5 / configuration-governance §2-§4: one env edge, frozen config, redacted repr."""
    monkeypatch.setenv("LLM_API_KEY", FAKE_KEY)

    config = load_provider_gateway_config()

    assert config.api_key == FAKE_KEY
    assert config.base_url == CITYU_BASE_URL
    assert config.chat_model == CHAT_MODEL
    assert FAKE_KEY not in repr(config)


def test_config_factory_fails_loud_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S5 / configuration-governance §3: a missing key fails loudly without a value."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        load_provider_gateway_config()

    message = str(excinfo.value)
    assert "LLM_API_KEY" in message
    assert FAKE_KEY not in message


def test_config_rejects_non_https_base_url() -> None:
    """S5 / configuration-governance §3: the bearer key is never sent over plaintext."""
    with pytest.raises(ValueError) as excinfo:
        ProviderGatewayConfig(
            api_key=FAKE_KEY,
            base_url="http://llm.cs.cityu.edu.hk/v1",
        )

    assert FAKE_KEY not in str(excinfo.value)


def test_only_config_module_reads_environment() -> None:
    """S5 / configuration-governance §5: config.py is the only environment reader."""
    offenders: list[tuple[Path, str]] = []

    for path in sorted((REPO_ROOT / "src/backend").rglob("*.py")):
        if path.resolve() == CONFIG_FILE.resolve():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
                offenders.append((path, node.attr))
            elif isinstance(node, ast.Name) and node.id == "getenv":
                offenders.append((path, node.id))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "dotenv":
                        offenders.append((path, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None and node.module.split(".")[0] == "dotenv":
                    offenders.append((path, node.module))

    assert offenders == []


def test_provider_gateway_imports_are_bounded() -> None:
    """ADR-001 / S4: no provider SDK, DB, API, auth, or safety-boundary import."""
    forbidden_roots = {
        "anthropic",
        "fastapi",
        "httpx",
        "openai",
        "psycopg",
        "psycopg2",
        "pydantic",
        "requests",
        "sqlalchemy",
    }
    forbidden_prefixes = (
        "backend.api",
        "backend.auth",
        "backend.database",
        "backend.grammar",
        "backend.safety_boundary",
        "backend.user_progress",
        "backend.vocabulary",
        "scripts",
    )

    tree = ast.parse(PROVIDER_FILE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_roots
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] not in forbidden_roots
            assert not node.module.startswith(forbidden_prefixes), node.module
        elif isinstance(node, ast.Name):
            assert node.id not in {"open", "getenv"}
        elif isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "getenv"}
