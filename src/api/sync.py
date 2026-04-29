# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from typing import Annotated

import structlog
from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel

from src.backends.base import StateBackend
from src.config import Settings
from src.core.models import RunStatus
from src.core.sync_engine import SyncEngine
from src.deps import get_settings, get_state_backend_dep, get_sync_engine

log = structlog.get_logger()
router = APIRouter()


class TriggerRequest(BaseModel):
    trigger_source: str = "api"


class TriggerResponse(BaseModel):
    run_id: str
    status: RunStatus
    events_processed: int
    duration_seconds: float
    adapter: str
    message: str


@router.post(
    "/trigger",
    responses={401: {"description": "Invalid or missing X-API-Key"}},
)
async def trigger_sync(
    trigger: Annotated[TriggerRequest, Body(embed=False)],
    settings: Annotated[Settings, Depends(get_settings)],
    engine: Annotated[SyncEngine, Depends(get_sync_engine)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> TriggerResponse:
    """
    Triggers a complete sync cycle synchronously.
    Requires X-API-Key header matching settings.api_secret_key.
    """
    if not x_api_key or x_api_key != settings.api_secret_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    record = engine.run_cycle(trigger_source=trigger.trigger_source)
    return TriggerResponse(
        run_id=record.run_id,
        status=record.status,
        events_processed=record.events_processed,
        duration_seconds=record.duration_seconds,
        adapter=record.adapter,
        message=f"Sync completed with status: {record.status.value}",
    )


@router.get("/status")
async def sync_status(
    state_backend: Annotated[StateBackend, Depends(get_state_backend_dep)] = None,
) -> dict:
    """Returns most recent run record summary."""
    runs = state_backend.list_recent_runs(limit=1)
    if not runs:
        return {"status": "no_runs", "last_run": None}
    last = runs[0]
    return {
        "status": last.status.value,
        "last_run": {
            "run_id": last.run_id,
            "started_at": last.started_at.isoformat(),
            "duration_seconds": last.duration_seconds,
            "events_processed": last.events_processed,
        },
    }
