"""Tutor - bounded model-provider adapter over an injected gateway.

Element: Tutor
Implements: ADR-001 §Decision; ADR-005 §Decision; ADR-006 §Decision;
FR-CHAT-001, NFR-PERF-001 (partial: bounded retry structure), NFR-COST-001.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.ai_companion.prompt_assembly import estimate_tokens
from backend.contracts.ai_companion import (
    InvalidRequestError,
    ModelGateway,
    ModelGatewayError,
    ModelRequest,
    ModelResponse,
    PromptBudgetExceeded,
    TaskType,
    TutorUnavailableError,
)


@dataclass(frozen=True)
class TutorConfig:
    """ADR-006 / RP-004: frozen provider bounds."""

    context_token_budget: int = 1500
    max_attempts: int = 3
    timeout_ms: int = 25000
    max_output_tokens: int = 700

    def __post_init__(self) -> None:
        if self.context_token_budget <= 0:
            raise ValueError("context_token_budget must be positive")
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        if not 5000 <= self.timeout_ms <= 60000:
            raise ValueError("timeout_ms must be between 5000 and 60000")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")


@dataclass(frozen=True)
class TutorRequest:
    """FR-CHAT-001: one already-assembled prompt to send to the gateway."""

    request_id: str
    prompt: str
    task: TaskType
    schema_id: str


@dataclass(frozen=True)
class TutorResult:
    """ADR-006: model output plus usage metadata for audit."""

    request_id: str
    text: str
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    attempts: int


class Tutor:
    """ADR-001: the only model-provider seam; no tool access and no write path."""

    def __init__(
        self,
        gateway: ModelGateway,
        config: TutorConfig | None = None,
    ) -> None:
        self._gateway = gateway
        self._config = config if config is not None else TutorConfig()

    def generate(self, request: TutorRequest) -> TutorResult:
        """Call the gateway within the prompt and retry bounds.

        Implements: ADR-006 §Decision; ADR-005 §Decision; NFR-COST-001,
        NFR-PERF-001 (partial).
        """
        self._validate_request(request)
        if estimate_tokens(request.prompt) > self._config.context_token_budget:
            raise PromptBudgetExceeded(
                f"prompt exceeds {self._config.context_token_budget} tokens"
            )

        model_request = ModelRequest(
            request_id=request.request_id,
            prompt=request.prompt,
            task=request.task,
            schema_id=request.schema_id,
            timeout_ms=self._config.timeout_ms,
            max_output_tokens=self._config.max_output_tokens,
        )

        last_error: ModelGatewayError | None = None
        for attempt in range(1, self._config.max_attempts + 1):
            try:
                response = self._gateway.complete(model_request)
            except ModelGatewayError as exc:
                last_error = exc
                if not exc.retryable or attempt == self._config.max_attempts:
                    raise TutorUnavailableError(
                        f"model gateway unavailable after {attempt} attempt(s)"
                    ) from exc
                continue
            except Exception as exc:
                raise TutorUnavailableError("model gateway failed") from exc

            self._validate_response(response)
            return TutorResult(
                request_id=request.request_id,
                text=response.text,
                model_id=response.model_id,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                attempts=attempt,
            )

        raise TutorUnavailableError("model gateway unavailable") from last_error

    def _validate_request(self, request: TutorRequest) -> None:
        if not request.request_id.strip():
            raise InvalidRequestError("request_id must be non-empty")
        if not request.prompt.strip():
            raise InvalidRequestError("prompt must be non-empty")
        if not request.schema_id.strip():
            raise InvalidRequestError("schema_id must be non-empty")

    def _validate_response(self, response: object) -> None:
        if not isinstance(response, ModelResponse):
            raise TutorUnavailableError("model gateway returned an invalid response")
        if not response.text.strip() or not response.model_id.strip():
            raise TutorUnavailableError("model gateway returned empty text or model id")
        if response.prompt_tokens < 0 or response.completion_tokens < 0:
            raise TutorUnavailableError("model gateway returned negative token usage")
