# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.auth.menu_access import post_login_redirect_url
from src.auth.request_realm import (
    NOT_ALLOWED_ORIGIN,
    REQUEST_REALM_HEADER,
    RequestRealmError,
    resolve_sso_redirect_uri,
)
from src.auth.session import clear_session, set_session_user
from src.auth.sso import SSOAccessDeniedError, WorkOSSSOService
from src.config import Settings
from src.deps import get_settings

log = structlog.get_logger()
router = APIRouter(tags=["auth"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: Annotated[str | None, Query()] = None,
    message: Annotated[str | None, Query()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> HTMLResponse:
    if not settings.sso_enabled:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": error, "message": message},
    )


@router.get("/auth/sso/initiate")
async def sso_initiate(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> RedirectResponse:
    realm = request.headers.get(REQUEST_REALM_HEADER)
    try:
        redirect_uri = resolve_sso_redirect_uri(settings, realm)
    except RequestRealmError:
        raise HTTPException(status_code=403, detail=NOT_ALLOWED_ORIGIN) from None

    state = secrets.token_hex(32)
    request.session["sso_state"] = state
    request.session["sso_redirect_uri"] = redirect_uri
    sso = WorkOSSSOService(settings)
    auth_url = sso.get_authorization_url(state, redirect_uri=redirect_uri)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/auth/callback", response_class=HTMLResponse, response_model=None)
async def sso_callback(
    request: Request,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> HTMLResponse | RedirectResponse:
    if error:
        log.warning("sso_callback_provider_error", error=error)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": error},
            status_code=200,
        )

    if not code or not state:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "missing_code_or_state"},
            status_code=200,
        )

    stored_state = request.session.pop("sso_state", None)
    if not stored_state or not secrets.compare_digest(stored_state, state):
        log.warning("sso_callback_state_mismatch")
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "invalid_state"},
            status_code=200,
        )

    sso = WorkOSSSOService(settings)
    try:
        user = sso.exchange_code(code)
    except SSOAccessDeniedError as exc:
        log.warning(
            "sso_access_denied",
            reason=exc.reason,
            detail=exc.detail,
        )
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": exc.reason, "error_detail": exc.detail},
            status_code=200,
        )
    except Exception as exc:
        log.warning("sso_callback_exchange_failed", error=str(exc))
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "auth_failed"},
            status_code=200,
        )

    set_session_user(request, user)
    log.info("sso_login_success", user_email=user.get("email"))
    return RedirectResponse(
        url=post_login_redirect_url(settings, user),
        status_code=303,
    )


@router.get("/auth/logout", response_class=HTMLResponse)
async def logout(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> HTMLResponse:
    clear_session(request)
    log.info("sso_logout")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"message": "logged_out"},
    )
