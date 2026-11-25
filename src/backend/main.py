"""AppEntry - composition root for the backend.

Element: AppEntry
Implements: INV-SEC-002 (zero upload routes); ADR-001 (guarded monolith);
  S5 (config only read at startup); ADR-011 (single service, PORT)

This module wires routers and exposes an application factory. It makes no
domain decision and never bypasses AuthSecurity or ProfileSchema. It registers
NO file-upload route: the only accepted content type is ``application/json``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Protocol, cast

from src.backend.auth.router import AuthRouter
from src.backend.auth.security import AuthSecurity
from src.backend.db.repositories import InMemoryStores, PostgresStores
from src.backend import config as backend_config

if TYPE_CHECKING:
    from fastapi import FastAPI


class RuntimeConfig(Protocol):
    """Configuration consumed by the application composition root.

    Implements: ADR-011; S5
    """

    database_url: str | None
    port: int


logger = logging.getLogger(__name__)


def build_stores(database_url: str | None) -> InMemoryStores | PostgresStores:
    """Build production stores over PostgreSQL, falling back to in-memory.

    Implements: ADR-011 (Render managed Postgres); ADR-009; INV-SEC-001
    The DSN must be the ``app_runtime`` role so corpus writes are denied. If a
    pool cannot be opened (driver missing or DB unreachable), the app degrades
    to in-memory stores and logs a warning rather than crashing at import time
    (RP-011 readiness still reports the DB state via /ready).
    """
    if not database_url:
        return InMemoryStores()
    try:
        from src.backend.db.repositories import PostgresStores, make_pool

        pool = make_pool(database_url)
        logger.info("database pool opened (PostgreSQL stores active)")
        return PostgresStores(pool)
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("database unavailable, using in-memory stores: %s", exc)
        return InMemoryStores()


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

    stores: InMemoryStores | PostgresStores = field(default_factory=InMemoryStores)
    security: AuthSecurity | None = None
    auth: AuthRouter | None = None

    def __post_init__(self) -> None:
        security = self.security
        if security is None:
            security = AuthSecurity(self.stores)
        self.security = security
        if self.auth is None:
            self.auth = AuthRouter(security=security, stores=self.stores)

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


def create_app(
    stores: InMemoryStores | PostgresStores | None = None,
) -> AppEntry:
    """Application factory used by the ASGI entrypoint and tests.

    Implements: ADR-001; ADR-011
    When ``stores`` is None the DATABASE_URL from config selects PostgreSQL
    stores with a graceful in-memory fallback.
    """
    if stores is not None:
        return AppEntry(stores=stores)
    try:
        load_config = cast(
            Callable[[], RuntimeConfig],
            getattr(backend_config, "load_config"),
        )
        database_url = load_config().database_url
    except Exception:  # pragma: no cover - config not exported in some tests
        database_url = None
    return AppEntry(stores=build_stores(database_url))


def build_fastapi_app() -> FastAPI:
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

    load_config = cast(
        Callable[[], RuntimeConfig],
        getattr(backend_config, "load_config"),
    )
    config = load_config()
    uvicorn.run(build_fastapi_app(), host="0.0.0.0", port=config.port)


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    run()
