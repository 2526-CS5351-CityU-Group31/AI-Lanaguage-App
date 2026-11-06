"""AppEntry - composition root for the backend.

Element: AppEntry
Implements: INV-SEC-002 (zero upload routes); ADR-001 (guarded monolith);
  S5 (config only read at startup); ADR-011 (single service, PORT)

This module wires routers and exposes an application factory. It makes no
domain decision and never bypasses AuthSecurity or ProfileSchema. It registers
NO file-upload route: the only accepted content type is ``application/json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.backend.auth.router import AuthRouter
from src.backend.auth.security_reference import ReferenceAuthSecurity
from src.backend.db.repositories import InMemoryStores


@dataclass(frozen=True)
class RouteSpec:
    """A registered route, used for introspection (e.g. upload-free checks).

    Implements: INV-SEC-002 (route introspection)
    """

    method: str
    path: str
    accepts_json_only: bool = True


@dataclass
class AppEntry:
    """Composition root: builds stores, security and routers.

    Implements: ADR-001; INV-SEC-002; ADR-011
    """

    stores: InMemoryStores = field(default_factory=InMemoryStores)
    security: object = None  # type: ignore[assignment]
    auth: AuthRouter = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.security is None:
            self.security = ReferenceAuthSecurity(self.stores)
        if self.auth is None:
            self.auth = AuthRouter(security=self.security, stores=self.stores)

    def routes(self) -> list[RouteSpec]:
        """Return the registered routes for introspection.

        Implements: INV-SEC-002 (no multipart/file routes)
        """
        return [
            RouteSpec("POST", "/auth/register"),
            RouteSpec("POST", "/auth/login"),
            RouteSpec("POST", "/auth/logout"),
            RouteSpec("GET", "/me"),
            RouteSpec("PATCH", "/me"),
            RouteSpec("GET", "/health"),
            RouteSpec("GET", "/ready"),
        ]

    def has_upload_routes(self) -> bool:
        """True if any route accepts file/multipart payloads.

        Implements: INV-SEC-002 (must be False)
        """
        return any(not route.accepts_json_only for route in self.routes())


def create_app(stores: InMemoryStores | None = None) -> AppEntry:
    """Application factory used by the ASGI entrypoint and tests.

    Implements: ADR-001; ADR-011
    """
    return AppEntry(stores=stores or InMemoryStores())


def build_fastapi_app() -> object:
    """Return the FastAPI ASGI application (server entrypoint).

    Implements: ADR-001; ADR-011; INV-SEC-002
    Delegates to the HTTP transport layer so the composition root stays free of
    framework-specific route logic.
    """
    from src.backend.api.app import build_http_app

    return build_http_app()


def run() -> None:
    """Start the ASGI server on the configured port (Render injects PORT).

    Implements: ADR-011; configuration-governance (PORT); S5
    """
    import uvicorn

    from src.backend.config import load_config

    config = load_config()
    uvicorn.run(build_fastapi_app(), host="0.0.0.0", port=config.port)


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    run()
