# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.adapters.base import BaseTargetAdapter
from src.backends.base import CursorBackend, StateBackend
from src.deps import get_adapter_dep, get_cursor_backend_dep, get_state_backend_dep

router = APIRouter()


@router.get("/")
async def liveness() -> dict:
    """Always 200. Used by ECS container health check."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    adapter: Annotated[BaseTargetAdapter, Depends(get_adapter_dep)],
    cursor_backend: Annotated[CursorBackend, Depends(get_cursor_backend_dep)],
    state_backend: Annotated[StateBackend, Depends(get_state_backend_dep)],
) -> JSONResponse:
    """
    Checks adapter + both backends.
    200 if all healthy, 503 if any component is unavailable.
    """
    components = {
        "adapter": adapter.health_check(),
        "cursor_backend": cursor_backend.health_check(),
        "state_backend": state_backend.health_check(),
    }
    all_healthy = all(components.values())
    status_code = 200 if all_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_healthy else "unavailable",
            "adapter": adapter.adapter_key,
            "components": components,
        },
    )
