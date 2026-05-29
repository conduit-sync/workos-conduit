# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from src.config import Settings

REQUEST_REALM_HEADER = "x-stakesmfg-request-realm"
NOT_ALLOWED_ORIGIN = "Not allowed origin"


class RequestRealmError(Exception):
    """Raised when the reverse-proxy realm header is missing or not permitted."""

    def __init__(self, message: str = NOT_ALLOWED_ORIGIN) -> None:
        self.message = message
        super().__init__(message)


def resolve_sso_redirect_uri(settings: Settings, realm: str | None) -> str:
    """Map X-Stakesmfg-Request-Realm to the WorkOS redirect URI for that origin."""
    normalized = (realm or "").strip().lower()
    if normalized == "internal":
        redirect_uri = settings.workos_redirect_url_internal.strip()
    elif normalized == "eastlake":
        redirect_uri = settings.workos_redirect_url_eastlake.strip()
    else:
        raise RequestRealmError()

    if not redirect_uri:
        raise RequestRealmError()
    return redirect_uri
