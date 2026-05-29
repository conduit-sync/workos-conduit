# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from fastapi import Depends, Request

from src.adapters.base import BaseTargetAdapter
from src.adapters.registry import get_adapter
from src.backends.base import CursorBackend, StateBackend
from src.backends.registry import get_cursor_backend, get_state_backend
from src.config import Settings, get_settings
from src.core.event_router import EventRouter
from src.core.sync_engine import SyncEngine
from src.handlers.registry import get_handlers
from src.workos.client import WorkOSEventsClient


def get_workos_client(settings: Settings = Depends(get_settings)) -> WorkOSEventsClient:
    return WorkOSEventsClient(settings)


def get_cursor_backend_dep(settings: Settings = Depends(get_settings)) -> CursorBackend:
    return get_cursor_backend(settings.cursor_backend, settings)


def get_state_backend_dep(settings: Settings = Depends(get_settings)) -> StateBackend:
    return get_state_backend(settings.state_backend, settings)


def get_adapter_dep(settings: Settings = Depends(get_settings)) -> BaseTargetAdapter:
    return get_adapter(settings.sync_target_adapter, settings)


def get_event_router() -> EventRouter:
    return EventRouter(handlers=get_handlers())


def get_dashboard_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict | None:
    if not settings.sso_enabled:
        return None
    from src.auth.session import get_session_user

    return get_session_user(request)


def get_sync_engine(
    settings: Settings = Depends(get_settings),
    workos_client: WorkOSEventsClient = Depends(get_workos_client),
    adapter: BaseTargetAdapter = Depends(get_adapter_dep),
    cursor_backend: CursorBackend = Depends(get_cursor_backend_dep),
    state_backend: StateBackend = Depends(get_state_backend_dep),
    event_router: EventRouter = Depends(get_event_router),
) -> SyncEngine:
    return SyncEngine(
        workos_client=workos_client,
        adapter=adapter,
        cursor_backend=cursor_backend,
        state_backend=state_backend,
        event_router=event_router,
        settings=settings,
    )
