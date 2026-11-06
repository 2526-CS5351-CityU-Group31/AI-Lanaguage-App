"""HTTP transport layer: Pydantic models and the FastAPI application factory.

Element: AppEntry (HTTP boundary; see main.py as the composition root)
Implements: FR-AUTH-001, FR-PROF-001; INV-AUTH-001 (via AuthSecurity);
  INV-LANG-001, INV-CEFR-001 (via ProfileSchema); INV-SEC-002 (JSON-only,
  zero upload routes); ADR-009; ADR-011

The transport layer performs no domain decision. It maps the AuthRouter's
typed results to JSON responses and maps its typed errors to HTTP status codes
(401/404/409/422). All request bodies are ``application/json``; there is no
multipart or file parameter anywhere in this module (INV-SEC-002).
"""

from __future__ import annotations

from fastapi import FastAPI, Header, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.backend.api.schemas.profile import ProfileValidationError
from src.backend.api.routers.chat import ChatRouter
from src.backend.auth.router import (
    AuthenticationError,
    AuthRouter,
    AuthorizationError,
    RegistrationConflict,
)
from src.backend.main import create_app as create_entry
from src.backend.safety_boundary.scope_guard_reference import ReferenceScopeGuard
from src.backend.user_progress.service import ProgressService
from src.backend.vocabulary.service import VocabularyService, VocabularyStateError


class _NoopPipeline:
    """Placeholder tutor pipeline: returns a validated-shaped stub turn.

    Implements: FR-CHAT-001 (wire point for the real RagPipeline, owned by
    Member 2). Makes no network call so offline runs stay deterministic.
    """

    def run(self, **kwargs: object) -> dict:
        return {
            "turn_id": str(kwargs.get("request_id", "turn")),
            "response": {"task": "conversation", "abstained": False, "source_ids": []},
            "source_ids": [],
        }


def _principal_of(request: Request):
    """Resolve the caller's principal from the bearer token or raise 401."""
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("missing session")
    token = authorization.split(" ", 1)[1].strip()
    principal = request.app.state.auth_router.resolve_principal(token)
    if principal is None:
        raise AuthenticationError("invalid session")
    return principal



class RegisterRequest(BaseModel):
    """Registration body. ``language`` is validated by ProfileSchema.

    Implements: FR-AUTH-001; INV-LANG-001, INV-CEFR-001
    """

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    cefr_level: str = Field(min_length=2, max_length=2)
    language: str = Field(default="en", min_length=2, max_length=2)


class LoginRequest(BaseModel):
    """Login body.

    Implements: FR-AUTH-001
    """

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UpdateProfileRequest(BaseModel):
    """Profile update body; both fields optional.

    Implements: FR-PROF-001; INV-CEFR-001
    """

    model_config = ConfigDict(extra="forbid")

    cefr_level: str | None = Field(default=None, max_length=2)
    learning_goals: str | None = Field(default=None, max_length=500)


class FamiliarityRequest(BaseModel):
    """Familiarity-state update body.

    Implements: FR-VOC-002
    """

    model_config = ConfigDict(extra="forbid")

    state: str = Field(min_length=1, max_length=20)


class MessageRequest(BaseModel):
    """A chat turn body.

    Implements: FR-CHAT-001
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=0, max_length=1500)
    request_id: str = Field(min_length=1, max_length=128)


class VocabularyCardResponse(BaseModel):
    """A published vocabulary card.

    Implements: FR-VOC-001
    """

    entry_id: str
    word: str
    sense: str
    level: str
    topic: str
    definition: str
    example: str


class ProgressResponse(BaseModel):
    """Dashboard aggregates derived from stored events.

    Implements: FR-DASH-001; INV-PROG-001
    """

    sessions: int
    words_reviewed: int
    mastered_vocabulary: int
    recent_topics: list[str]


class TokenResponse(BaseModel):
    """Session token response.

    Implements: FR-AUTH-001
    """

    session_token: str


class ProfileResponse(BaseModel):
    """Owner-scoped profile projection.

    Implements: FR-PROF-001
    """

    user_id: str
    email: str
    cefr_level: str
    language: str
    learning_goals: str | None = None


def _auth_of(request: Request) -> AuthRouter:
    """Return the injected AuthRouter from application state."""
    return request.app.state.auth_router


def _extract_bearer(authorization: str | None) -> str:
    """Extract the token from an ``Authorization: Bearer <token>`` header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("missing session")
    return authorization.split(" ", 1)[1].strip()


def build_http_app(router: AuthRouter | None = None) -> FastAPI:
    """Build the FastAPI application around an ``AuthRouter``.

    Implements: ADR-001; ADR-011; INV-SEC-002 (no upload routes registered)
    """
    entry = create_entry()
    auth_router = router or entry.auth

    app = FastAPI(title="AI-Companion Language Learning API", version="1.0.0")
    app.state.auth_router = auth_router
    app.state.stores = entry.stores
    app.state.vocabulary_service = VocabularyService(entry.stores)
    app.state.progress_service = ProgressService(entry.stores)
    app.state.scope_guard = ReferenceScopeGuard()
    app.state.chat_router = ChatRouter(
        security=entry.security,
        scope_guard=app.state.scope_guard,
        pipeline_factory=lambda: _NoopPipeline(),
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe (static 200). Implements: RP-011; ADR-011."""
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        """Readiness probe; the in-memory store is always ready here.

        Implements: RP-011; ADR-011
        """
        return {"status": "ready"}

    @app.post("/auth/register", response_model=TokenResponse)
    def register(body: RegisterRequest, request: Request) -> TokenResponse:
        """Implements: FR-AUTH-001; INV-LANG-001, INV-CEFR-001; RP-015."""
        auth = _auth_of(request)
        try:
            token = auth.register(
                email=body.email,
                password=body.password,
                cefr_level=body.cefr_level,
                language=body.language,
            )
        except ProfileValidationError as exc:
            return JSONResponse(status_code=exc.status_code, content={exc.field: exc.reason})
        except RegistrationConflict as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.reason})
        return TokenResponse(session_token=token)

    @app.post("/auth/login", response_model=TokenResponse)
    def login(body: LoginRequest, request: Request) -> TokenResponse:
        """Implements: FR-AUTH-001; RP-012."""
        auth = _auth_of(request)
        try:
            token = auth.login(email=body.email, password=body.password)
        except AuthenticationError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.reason})
        return TokenResponse(session_token=token)

    @app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Response:
        """Implements: FR-AUTH-001."""
        auth = _auth_of(request)
        try:
            token = _extract_bearer(authorization)
        except AuthenticationError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.reason})
        auth.logout(token)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/me", response_model=ProfileResponse)
    def get_me(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> ProfileResponse:
        """Implements: FR-PROF-001; INV-AUTH-001."""
        auth = _auth_of(request)
        try:
            token = _extract_bearer(authorization)
            profile = auth.get_profile(token)
        except AuthenticationError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.reason})
        except AuthorizationError:
            return JSONResponse(status_code=404, content={})
        return ProfileResponse(**profile.__dict__)

    @app.patch("/me", response_model=ProfileResponse)
    def update_me(
        body: UpdateProfileRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> ProfileResponse:
        """Implements: FR-PROF-001; INV-CEFR-001; RP-015."""
        auth = _auth_of(request)
        try:
            token = _extract_bearer(authorization)
            profile = auth.update_profile(
                token, cefr_level=body.cefr_level, learning_goals=body.learning_goals
            )
        except AuthenticationError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.reason})
        except ProfileValidationError as exc:
            return JSONResponse(status_code=exc.status_code, content={exc.field: exc.reason})
        except AuthorizationError:
            return JSONResponse(status_code=404, content={})
        return ProfileResponse(**profile.__dict__)

    @app.get("/vocabulary/random", response_model=list[VocabularyCardResponse])
    def vocabulary_random(
        request: Request,
        level: str = "A1",
        count: int = 5,
        seed: int = 0,
        topic: str | None = None,
    ) -> list[VocabularyCardResponse]:
        """Return seeded published vocabulary cards for a level.

        Implements: FR-VOC-001 (published-only; identical seed -> identical)
        """
        loader = request.app.state.stores.loader
        if loader is None:
            return JSONResponse(status_code=503, content={"error": "vocabulary dataset not loaded"})
        cards = loader.select_random(level=level, count=count, seed=seed, topic=topic)
        return [VocabularyCardResponse(**card.__dict__) for card in cards]

    @app.post("/me/vocabulary/{entry_id}")
    def record_vocabulary(
        entry_id: str,
        body: FamiliarityRequest,
        request: Request,
    ) -> dict[str, str]:
        """Record familiarity state for the owner and emit an event.

        Implements: FR-VOC-002; ADR-008; INV-AUTH-001 (owner-scoped)
        """
        try:
            principal = _principal_of(request)
            record = request.app.state.vocabulary_service.record_familiarity(
                user_id=principal.user_id, entry_id=entry_id, state=body.state
            )
        except AuthenticationError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.reason})
        except VocabularyStateError as exc:
            return JSONResponse(status_code=exc.status_code, content=exc.body)
        return {"user_id": record.user_id, "entry_id": record.entry_id, "state": record.state}

    @app.get("/me/progress", response_model=ProgressResponse)
    def progress(request: Request) -> ProgressResponse:
        """Aggregate dashboard totals from stored events for the owner.

        Implements: FR-DASH-001; INV-PROG-001 (never model-derived)
        """
        try:
            principal = _principal_of(request)
        except AuthenticationError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.reason})
        metrics = request.app.state.progress_service.dashboard(user_id=principal.user_id)
        return ProgressResponse(
            sessions=metrics.sessions,
            words_reviewed=metrics.words_reviewed,
            mastered_vocabulary=metrics.mastered_vocabulary,
            recent_topics=metrics.recent_topics,
        )

    @app.post("/sessions/{session_id}/messages")
    def post_message(
        session_id: str,
        body: MessageRequest,
        request: Request,
    ):
        """Scope-guard the message, then (only if accepted) run the pipeline.

        Implements: INV-SCOPE-001, INV-SCOPE-003; FR-CHAT-001
        """
        authorization = request.headers.get("authorization")
        if not authorization or not authorization.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"error": "missing session"})
        token = authorization.split(" ", 1)[1].strip()
        try:
            result = request.app.state.chat_router.handle_message(
                token,
                session_id=session_id,
                message=body.message,
                request_id=body.request_id,
            )
        except AuthenticationError as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": exc.reason})
        if isinstance(result, dict):
            return JSONResponse(status_code=200, content=result)
        return {
            "session_id": result.session_id,
            "turn_id": result.turn_id,
            "response": result.response,
            "source_ids": list(result.source_ids),
        }

    return app
