# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from src.api import health, runs, sync
from src.config import get_settings
from src.dashboard.login_router import router as dashboard_login_router
from src.dashboard.oauth_router import router as dashboard_oauth_router
from src.dashboard.portal_router import router as dashboard_portal_router
from src.dashboard.router import router as dashboard_router
from src.logging_config import configure_logging

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    configure_logging(settings)
    log.info(
        "workos_conduit_started",
        adapter=settings.sync_target_adapter,
        cursor_backend=settings.cursor_backend,
        state_backend=settings.state_backend,
        dashboard_enabled=settings.dashboard_enabled,
        version="1.0.0",
    )
    yield
    log.info("workos_conduit_stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="WorkOS Conduit",
        description="Generic user provisioning bridge: WorkOS → third-party targets",
        version="1.0.0",
        license_info={
            "name": "GPL-3.0-or-later",
            "url": "https://www.gnu.org/licenses/gpl-3.0",
        },
        lifespan=lifespan,
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.dashboard_sso_session_secret,
        session_cookie="conduit_session",
        https_only=False,
        same_site="lax",
    )

    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(sync.router, prefix="/api/v1/sync", tags=["sync"])
    app.include_router(runs.router, prefix="/api/v1/runs", tags=["runs"])
    app.include_router(dashboard_router, tags=["dashboard"])
    app.include_router(dashboard_portal_router)
    app.include_router(dashboard_oauth_router)
    app.include_router(dashboard_login_router)

    return app


app = create_app()
