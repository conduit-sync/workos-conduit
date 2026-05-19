# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from src.adapters.ninjaone.refresh_token_store import (
    RefreshTokenRecord,
    SsmRefreshTokenStore,
)
from src.config import Settings
from src.deps import get_settings

log = structlog.get_logger()
router = APIRouter(prefix="/dashboard/oauth/ninjaone", tags=["dashboard"])

_STATE_TTL_SECONDS = 600
_oauth_state_cache: dict[str, datetime] = {}


class OAuthStartResponse(BaseModel):
    authorize_url: str


def _prune_state_cache(now: datetime) -> None:
    expired = [
        state
        for state, issued_at in _oauth_state_cache.items()
        if (now - issued_at).total_seconds() > _STATE_TTL_SECONDS
    ]
    for state in expired:
        _oauth_state_cache.pop(state, None)


def _ensure_api_key(settings: Settings, x_api_key: str | None, *, source: str) -> None:
    if not x_api_key or x_api_key != settings.api_secret_key:
        log.warning("dashboard_oauth_unauthorized", source=source)
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@router.post("/start")
async def oauth_start(
    response: Response,
    settings: Settings = Depends(get_settings),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> OAuthStartResponse:
    _ensure_api_key(settings, x_api_key, source="dashboard_oauth_start")
    if not settings.ninjaone_oauth_refresh_token_ssm_param.strip():
        raise HTTPException(
            status_code=400,
            detail="NINJAONE_OAUTH_REFRESH_TOKEN_SSM_PARAM must be set to enable dashboard OAuth flow",
        )
    if not settings.dashboard_public_base_url:
        raise HTTPException(
            status_code=400,
            detail="DASHBOARD_PUBLIC_BASE_URL must be set for dashboard OAuth flow",
        )

    now = datetime.now(tz=UTC)
    _prune_state_cache(now)
    state = secrets.token_hex(32)
    _oauth_state_cache[state] = now

    redirect_uri = (
        f"{settings.dashboard_public_base_url.rstrip('/')}"
        f"{settings.ninjaone_oauth_redirect_path}"
    )
    authorize_url = (
        f"{settings.ninjaone_base_url.rstrip('/')}{settings.ninjaone_oauth_authorize_path}?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": settings.ninjaone_oauth_client_id,
                "redirect_uri": redirect_uri,
                "scope": settings.ninjaone_oauth_scope,
                "state": state,
            }
        )
    )
    response.set_cookie(
        key="ninjaone_oauth_state",
        value=state,
        max_age=_STATE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return OAuthStartResponse(authorize_url=authorize_url)


@router.get("/callback")
async def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state_cookie: str | None = Cookie(default=None, alias="ninjaone_oauth_state"),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if not settings.ninjaone_oauth_refresh_token_ssm_param.strip():
        return RedirectResponse(
            url="/?oauth_status=error&detail=oauth_ssm_param_not_configured",
            status_code=303,
        )
    if error:
        return RedirectResponse(
            url=f"/?oauth_status=error&detail={error}", status_code=303
        )
    if not code or not state:
        return RedirectResponse(
            url="/?oauth_status=error&detail=missing_code_or_state", status_code=303
        )

    now = datetime.now(tz=UTC)
    _prune_state_cache(now)
    issued_at = _oauth_state_cache.pop(state, None)
    if not issued_at or (now - issued_at) > timedelta(seconds=_STATE_TTL_SECONDS):
        return RedirectResponse(
            url="/?oauth_status=error&detail=invalid_state", status_code=303
        )
    if state_cookie != state:
        return RedirectResponse(
            url="/?oauth_status=error&detail=state_cookie_mismatch", status_code=303
        )

    redirect_uri = (
        f"{settings.dashboard_public_base_url.rstrip('/')}"
        f"{settings.ninjaone_oauth_redirect_path}"
    )
    try:
        response = httpx.post(
            f"{settings.ninjaone_base_url.rstrip('/')}{settings.ninjaone_oauth_token_path}",
            headers={"accept": "application/json"},
            data={
                "grant_type": "authorization_code",
                "client_id": settings.ninjaone_oauth_client_id,
                "client_secret": settings.ninjaone_oauth_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        refresh_token = payload.get("refresh_token")
        if not refresh_token:
            raise ValueError("missing_refresh_token")

        record = RefreshTokenRecord.from_refresh_token(
            refresh_token=refresh_token,
            scope=settings.ninjaone_oauth_scope,
            lifetime_days=settings.ninjaone_oauth_refresh_token_lifetime_days,
            issuer="dashboard",
        )
        SsmRefreshTokenStore(settings).put(record)
    except Exception as exc:
        log.warning("dashboard_oauth_callback_failed", error=str(exc))
        return RedirectResponse(
            url=f"/?oauth_status=error&detail={str(exc)}", status_code=303
        )

    return RedirectResponse(url="/?oauth_status=success", status_code=303)
