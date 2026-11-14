"""CityU provider gateway - concrete ``ModelGateway`` adapter over HTTPS.

Element: support adapter for the existing Tutor element (``ModelGateway`` port);
this file is not a new architectural element.
Implements: ADR-001 §Decision (advisory-only provider seam); ADR-005 §Decision
(structured output requested, acceptance remains downstream); ADR-006 §Decision
(bounded prompt/output and usage recording); FR-CHAT-001,
NFR-COST-001 (partial: usage is recorded, not enforced here),
NFR-PERF-001 (partial: the request timeout is bounded here, latency is not
measured), INV-CITE-001 (support: the gateway never validates or repairs model
output).

The gateway makes exactly one HTTP attempt per ``complete`` call. ``Tutor`` is
the sole retry authority. Provider text is returned unchanged so the existing
``CitationValidator`` remains the only acceptance gate.
"""

from __future__ import annotations

import http.client
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from backend.config import ProviderGatewayConfig
from backend.contracts.ai_companion import (
    InvalidRequestError,
    ModelGatewayError,
    ModelPermanentError,
    ModelRateLimitError,
    ModelRequest,
    ModelResponse,
    ModelTimeoutError,
)

CHAT_COMPLETIONS_PATH = "/chat/completions"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderHttpRequest:
    """ADR-001 / S5: one injected HTTP POST request.

    ``headers`` and ``body`` are excluded from ``repr`` so a request can never
    disclose the bearer key or the assembled prompt in a log or traceback.
    """

    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)
    timeout_seconds: float


@dataclass(frozen=True)
class ProviderHttpResponse:
    """ADR-001: one injected HTTP response.

    ``body`` is excluded from ``repr`` so provider content cannot leak through
    an accidental log of the response object.
    """

    status_code: int
    body: bytes = field(repr=False)


class HttpTransport(Protocol):
    """ADR-001 / S5: injected transport seam; offline tests supply canned responses.

    Implementations return a response for any HTTP status. A timeout is raised
    as ``TimeoutError``; a DNS, connection, TLS or protocol failure is raised as
    ``OSError``. No implementation may be called with an unbounded timeout.
    """

    def post(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        """Send one POST request and return the provider response."""
        ...


class UrllibHttpTransport:
    """ADR-001: standard-library HTTPS transport with default TLS verification."""

    def post(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        """POST the request with ``urlopen`` and a bounded socket timeout.

        Implements: ADR-001 §Decision; RP-004. HTTP error bodies are never read.
        """
        http_request = urllib.request.Request(
            url=request.url,
            data=request.body,
            headers=dict(request.headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                http_request,
                timeout=request.timeout_seconds,
            ) as response:
                status_code = response.getcode()
                body = response.read()
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            exc.close()
            return ProviderHttpResponse(status_code=status_code, body=b"")
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError("provider request timed out") from None
            raise OSError("provider connection failed") from None
        except TimeoutError:
            raise TimeoutError("provider request timed out") from None
        except (OSError, http.client.HTTPException):
            raise OSError("provider connection failed") from None

        if not isinstance(status_code, int):
            raise OSError("provider returned no status")
        if not isinstance(body, bytes):
            raise OSError("provider returned an invalid body")
        return ProviderHttpResponse(status_code=status_code, body=body)


@dataclass(frozen=True)
class _ParsedCompletion:
    """ADR-005/ADR-006: provider fields accepted by the gateway."""

    text: str
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    usage_present: bool


class CityUModelGateway:
    """ADR-001: concrete advisory ``ModelGateway`` for the CityU endpoint."""

    def __init__(
        self,
        config: ProviderGatewayConfig,
        transport: HttpTransport,
    ) -> None:
        self._config = config
        self._transport = transport

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Make one bounded structured-output request and map failures.

        Implements: ADR-005 §Decision; ADR-006 §Decision; RP-004/RP-009;
        FR-CHAT-001, NFR-PERF-001 (partial), NFR-COST-001 (partial).
        """
        self._validate_request(request)
        started = time.monotonic()

        try:
            http_response = self._transport.post(
                ProviderHttpRequest(
                    url=(
                        f"{self._config.base_url.rstrip('/')}"
                        f"{CHAT_COMPLETIONS_PATH}"
                    ),
                    headers=self._headers(),
                    body=self._build_body(request),
                    timeout_seconds=request.timeout_ms / 1000.0,
                )
            )
        except TimeoutError:
            self._log_failure(
                request.request_id,
                None,
                retryable=True,
                latency_ms=_elapsed_ms(started),
            )
            raise ModelTimeoutError() from None
        except OSError:
            self._log_failure(
                request.request_id,
                None,
                retryable=True,
                latency_ms=_elapsed_ms(started),
            )
            raise ModelGatewayError(
                "provider connection failed",
                retryable=True,
            ) from None

        latency_ms = _elapsed_ms(started)
        self._raise_for_status(
            http_response.status_code,
            request_id=request.request_id,
            latency_ms=latency_ms,
        )

        parsed = self._parse_completion(http_response.body)
        if parsed is None:
            self._log_failure(
                request.request_id,
                http_response.status_code,
                retryable=False,
                latency_ms=latency_ms,
            )
            raise ModelPermanentError("provider returned a malformed response")

        self._log_success(
            request.request_id,
            parsed,
            status_code=http_response.status_code,
            latency_ms=latency_ms,
        )
        return ModelResponse(
            text=parsed.text,
            model_id=parsed.model_id,
            prompt_tokens=parsed.prompt_tokens,
            completion_tokens=parsed.completion_tokens,
        )

    def _validate_request(self, request: ModelRequest) -> None:
        if not request.prompt.strip():
            raise InvalidRequestError("prompt must be non-empty")
        if request.timeout_ms <= 0:
            raise InvalidRequestError("timeout_ms must be positive")
        if request.max_output_tokens <= 0:
            raise InvalidRequestError("max_output_tokens must be positive")
        if not 0.0 <= request.temperature <= 1.0:
            raise InvalidRequestError("temperature must be between 0.0 and 1.0")

    def _headers(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def _build_body(self, request: ModelRequest) -> bytes:
        payload: dict[str, object] = {
            "model": self._config.chat_model,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def _raise_for_status(
        self,
        status_code: int,
        *,
        request_id: str,
        latency_ms: int,
    ) -> None:
        if 200 <= status_code < 300:
            return
        if status_code in (408, 504):
            self._log_failure(
                request_id,
                status_code,
                retryable=True,
                latency_ms=latency_ms,
            )
            raise ModelTimeoutError()
        if status_code == 429:
            self._log_failure(
                request_id,
                status_code,
                retryable=True,
                latency_ms=latency_ms,
            )
            raise ModelRateLimitError()
        if 500 <= status_code < 600:
            self._log_failure(
                request_id,
                status_code,
                retryable=True,
                latency_ms=latency_ms,
            )
            raise ModelGatewayError(
                f"provider returned HTTP {status_code}",
                retryable=True,
            )
        self._log_failure(
            request_id,
            status_code,
            retryable=False,
            latency_ms=latency_ms,
        )
        raise ModelPermanentError(f"provider returned HTTP {status_code}")

    def _parse_completion(self, body: bytes) -> _ParsedCompletion | None:
        try:
            decoded = body.decode("utf-8")
            payload = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

        payload_map = _as_string_mapping(payload)
        if payload_map is None:
            return None

        choices = payload_map.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first_choice = _as_string_mapping(choices[0])
        if first_choice is None:
            return None
        message = _as_string_mapping(first_choice.get("message"))
        if message is None:
            return None
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return None

        model_value = payload_map.get("model")
        model_id = (
            model_value.strip()
            if isinstance(model_value, str) and model_value.strip()
            else self._config.chat_model
        )

        prompt_tokens = 0
        completion_tokens = 0
        usage_present = False
        usage = _as_string_mapping(payload_map.get("usage"))
        if usage is not None:
            prompt_value = _token_count(usage.get("prompt_tokens"))
            completion_value = _token_count(usage.get("completion_tokens"))
            if prompt_value is not None and completion_value is not None:
                prompt_tokens = prompt_value
                completion_tokens = completion_value
                usage_present = True

        return _ParsedCompletion(
            text=content,
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            usage_present=usage_present,
        )

    def _log_success(
        self,
        request_id: str,
        parsed: _ParsedCompletion,
        *,
        status_code: int,
        latency_ms: int,
    ) -> None:
        _LOGGER.info(
            "provider gateway call completed request_id=%s model_id=%s "
            "latency_ms=%d prompt_tokens=%d completion_tokens=%d "
            "status_code=%d usage_present=%s",
            request_id,
            parsed.model_id,
            latency_ms,
            parsed.prompt_tokens,
            parsed.completion_tokens,
            status_code,
            parsed.usage_present,
        )

    def _log_failure(
        self,
        request_id: str,
        status_code: int | None,
        *,
        retryable: bool,
        latency_ms: int,
    ) -> None:
        _LOGGER.warning(
            "provider gateway call failed request_id=%s status_code=%s "
            "latency_ms=%d retryable=%s",
            request_id,
            status_code if status_code is not None else "none",
            latency_ms,
            retryable,
        )


def _as_string_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _token_count(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
