# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from workos._errors import APIError

from src.auth.action_auth import authorize_dashboard_action
from src.auth.menu_access import NAV_PORTAL
from src.config import Settings
from src.dashboard.access import require_dashboard_login, require_nav_access, template_nav_context
from src.deps import get_dashboard_user, get_settings
from src.workos.portal_users import PortalUsersService

log = structlog.get_logger()
router = APIRouter(tags=["dashboard"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/portal/users", response_class=HTMLResponse)
async def portal_users_page(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: Annotated[dict | None, Depends(get_dashboard_user)] = None,
) -> HTMLResponse:
    nav_denied = require_nav_access(request, settings, current_user, NAV_PORTAL)
    if nav_denied:
        return nav_denied

    portal_enabled = settings.customer_portal_enabled
    users: list = []
    load_error: str | None = None
    created = request.query_params.get("created")
    error = request.query_params.get("error")

    if portal_enabled:
        try:
            users = PortalUsersService(settings).list_users()
        except Exception as exc:
            load_error = str(exc)
            log.warning("portal_users_list_failed", error=load_error)

    return templates.TemplateResponse(
        request,
        "portal_users.html",
        {
            "active_nav": "portal",
            "current_user": current_user,
            **template_nav_context(settings, current_user),
            "portal_enabled": portal_enabled,
            "organization_id": settings.workos_customer_portal_organization_id,
            "invite_role_slug": settings.customer_portal_invite_role_slug,
            "client_id_metadata_key": settings.workos_customer_portal_user_client_id_metadata_key,
            "users": users,
            "load_error": load_error,
            "created_email": created,
            "form_error": error,
        },
    )


@router.post("/portal/users", response_model=None)
async def portal_users_create(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: Annotated[dict | None, Depends(get_dashboard_user)],
    email: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> HTMLResponse | RedirectResponse:
    login_denied = require_dashboard_login(request, settings, current_user)
    if login_denied:
        return login_denied

    nav_denied = require_nav_access(request, settings, current_user, NAV_PORTAL)
    if nav_denied:
        return nav_denied

    try:
        authorize_dashboard_action(request, settings, x_api_key)
    except HTTPException:
        return RedirectResponse(
            url="/portal/users?error=Unauthorized",
            status_code=303,
        )

    if not settings.customer_portal_enabled:
        return RedirectResponse(
            url="/portal/users?error=portal_not_configured",
            status_code=303,
        )

    try:
        PortalUsersService(settings).invite_user(email=email, client_id=client_id)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/portal/users?error={quote(str(exc))}",
            status_code=303,
        )
    except APIError as exc:
        log.warning("portal_user_invite_failed", error=str(exc))
        return RedirectResponse(
            url=f"/portal/users?error={quote(str(exc))}",
            status_code=303,
        )
    except Exception as exc:
        log.warning("portal_user_invite_failed", error=str(exc))
        return RedirectResponse(
            url=f"/portal/users?error={quote(str(exc))}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/portal/users?created={quote(email.strip())}",
        status_code=303,
    )
