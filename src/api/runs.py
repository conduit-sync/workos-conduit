# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.backends.base import StateBackend
from src.core.models import RunRecord
from src.deps import get_state_backend_dep

router = APIRouter()


@router.get("/", response_model=list[RunRecord])
async def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    state_backend: StateBackend = Depends(get_state_backend_dep),
) -> list[RunRecord]:
    """Returns `limit` most recent runs, most recent first."""
    return state_backend.list_recent_runs(limit=limit)


@router.get("/{run_id}", response_model=RunRecord)
async def get_run(
    run_id: str,
    state_backend: StateBackend = Depends(get_state_backend_dep),
) -> RunRecord:
    """Returns single run by run_id. 404 if not found."""
    record = state_backend.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return record
