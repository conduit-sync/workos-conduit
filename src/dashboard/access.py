# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.auth.menu_access import (
    NAV_PORTAL,
    NAV_SYNC,
    can_access_nav,
    directory_roles_from_user,
    nav_access_context,
)
from src.config import Settings

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def require_dashboard_login(
    request: Request,
    settings: Settings,
    current_user: dict | None,
) -> HTMLResponse | None:
    if not settings.dashboard_enabled:
        raise HTTPException(status_code=404, detail="Dashboard disabled")
    if settings.sso_enabled and current_user is None:
        return templates.TemplateResponse(request, "login.html", {}, status_code=200)
    return None


def require_nav_access(
    request: Request,
    settings: Settings,
    current_user: dict | None,
    nav: str,
) -> HTMLResponse | RedirectResponse | None:
    """Return a response when the user cannot access this nav section."""
    denied = require_dashboard_login(request, settings, current_user)
    if denied:
        return denied

    if not settings.sso_enabled:
        return None

    roles = directory_roles_from_user(current_user)
    if can_access_nav(roles, settings, nav):
        return None

    if nav == NAV_SYNC and can_access_nav(roles, settings, NAV_PORTAL):
        return RedirectResponse(url="/portal/users", status_code=303)

    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": "section_access_denied",
            "error_detail": f"You do not have permission to access this section ({nav}).",
        },
        status_code=403,
    )


def template_nav_context(settings: Settings, current_user: dict | None) -> dict:
    return nav_access_context(settings, current_user)
