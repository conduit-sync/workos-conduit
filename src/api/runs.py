# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.backends.base import StateBackend
from src.core.models import RunRecord
from src.deps import get_state_backend_dep

router = APIRouter()


@router.get("/")
async def list_runs(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    state_backend: Annotated[StateBackend, Depends(get_state_backend_dep)] = None,
) -> list[RunRecord]:
    """Returns `limit` most recent runs, most recent first."""
    return state_backend.list_recent_runs(limit=limit)


@router.get(
    "/{run_id}",
    responses={404: {"description": "Run not found"}},
)
async def get_run(
    run_id: str,
    state_backend: Annotated[StateBackend, Depends(get_state_backend_dep)] = None,
) -> RunRecord:
    """Returns single run by run_id. 404 if not found."""
    record = state_backend.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return record
