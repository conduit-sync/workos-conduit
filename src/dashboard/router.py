# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.backends.base import StateBackend
from src.config import Settings
from src.core.models import RunRecord, RunStatus, SyncAction
from src.deps import get_settings, get_state_backend_dep

log = structlog.get_logger()
router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _compute_health(runs: list[RunRecord]) -> str:
    if not runs:
        return "unknown"
    last_five = runs[:5]
    if runs[0].status == RunStatus.ERROR:
        return "down"
    if any(r.status == RunStatus.PARTIAL_FAILURE for r in last_five):
        return "degraded"
    if all(r.status == RunStatus.SUCCESS for r in last_five):
        return "healthy"
    return "degraded"


def _count_events_last_24h(runs: list[RunRecord]) -> int:
    cutoff = datetime.now(tz=UTC) - timedelta(hours=24)
    return sum(r.events_processed for r in runs if r.started_at >= cutoff)


def _safe_config(settings: Settings) -> dict:
    """Returns non-sensitive config values for display on the dashboard."""
    import json

    try:
        allowed = json.loads(settings.sync_allowed_groups)
    except Exception:
        allowed = []

    try:
        role_map = json.loads(settings.ninjaone_group_role_map) if settings.ninjaone_group_role_map_source == "env" else None
    except Exception:
        role_map = {}

    from src.workos.client import _parse_event_types
    try:
        event_types = _parse_event_types(settings.workos_event_types)
    except Exception:
        event_types = [
            "dsync.user.created", "dsync.user.updated", "dsync.user.deleted",
            "dsync.group.user_added", "dsync.group.user_removed",
        ]

    return {
        "adapter": settings.sync_target_adapter,
        "cursor_backend": settings.cursor_backend,
        "state_backend": settings.state_backend,
        "workos_directory_id": settings.workos_directory_id,
        "workos_event_types": event_types,
        "workos_events_page_size": settings.workos_events_page_size,
        "allowed_groups": allowed,
        "allowed_groups_source": settings.sync_allowed_groups_source,
        "role_map": role_map,
        "role_map_source": settings.ninjaone_group_role_map_source,
        "stop_on_error": settings.sync_stop_on_error,
        "ninjaone_base_url": settings.ninjaone_base_url,
        "s3_state_bucket": settings.s3_state_bucket or None,
        "log_level": settings.log_level,
    }


def _compute_action_totals(runs: list[RunRecord]) -> dict[str, int]:
    totals: dict[str, int] = {action.value: 0 for action in SyncAction}
    for run in runs:
        for action_val, count in run.counts.items():
            totals[action_val] = totals.get(action_val, 0) + count
    return totals


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    state_backend: StateBackend = Depends(get_state_backend_dep),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not settings.dashboard_enabled:
        raise HTTPException(status_code=404, detail="Dashboard disabled")

    backend_error: str | None = None
    runs: list[RunRecord] = []
    try:
        runs = state_backend.list_recent_runs(limit=settings.dashboard_run_history_limit)
    except Exception as exc:
        backend_error = str(exc)
        log.warning("dashboard_backend_unavailable", error=backend_error)

    action_totals = _compute_action_totals(runs)
    total = sum(action_totals.values()) or 1
    action_pcts = {k: round(v / total * 100, 1) for k, v in action_totals.items()}

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "runs": runs,
            "total_runs": len(runs),
            "last_run": runs[0] if runs else None,
            "health": _compute_health(runs),
            "events_last_24h": _count_events_last_24h(runs),
            "adapter": settings.sync_target_adapter,
            "action_totals": action_totals,
            "action_pcts": action_pcts,
            "dashboard_auto_refresh_seconds": settings.dashboard_auto_refresh_seconds,
            "backend_error": backend_error,
            "config": _safe_config(settings),
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(
    run_id: str,
    request: Request,
    state_backend: StateBackend = Depends(get_state_backend_dep),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not settings.dashboard_enabled:
        raise HTTPException(status_code=404, detail="Dashboard disabled")
    try:
        record = state_backend.get_run(run_id)
    except Exception as exc:
        log.warning("dashboard_backend_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail=f"State backend unavailable: {exc}") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "run": record,
            "dashboard_auto_refresh_seconds": settings.dashboard_auto_refresh_seconds,
            "config": _safe_config(settings),
        },
    )
