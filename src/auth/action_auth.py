# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from src.auth.session import get_session_user
from src.config import Settings, get_settings


def authorize_dashboard_action(
    request: Request,
    settings: Settings,
    x_api_key: str | None,
) -> None:
    """Allow privileged dashboard actions via API key or SSO session."""
    if x_api_key and secrets.compare_digest(x_api_key, settings.api_secret_key):
        return
    if settings.sso_enabled and get_session_user(request):
        return
    raise HTTPException(
        status_code=401,
        detail="Invalid or missing authentication (X-API-Key or SSO session)",
    )


def require_dashboard_or_api_key(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    authorize_dashboard_action(request, settings, x_api_key)
