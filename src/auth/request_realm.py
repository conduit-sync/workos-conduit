# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from src.config import Settings

REQUEST_REALM_HEADER = "x-stakesmfg-request-realm"
NOT_ALLOWED_ORIGIN = "Not allowed origin"
_REALM_INTERNAL = "internal"
_REALM_EASTLAKE = "eastlake"
WORKOS_SSO_CALLBACK_PATH = "/auth/callback"


class RequestRealmError(Exception):
    """Raised when the reverse-proxy realm header is missing or not permitted."""

    def __init__(self, message: str = NOT_ALLOWED_ORIGIN) -> None:
        self.message = message
        super().__init__(message)


def normalized_request_realm(settings: Settings, realm: str | None) -> str:
    """Resolve realm from header, with optional local-dev default when header is absent."""
    value = (realm or "").strip().lower()
    if not value:
        value = settings.request_realm_default.strip().lower()
    if value not in (_REALM_INTERNAL, _REALM_EASTLAKE):
        raise RequestRealmError()
    return value


def public_base_url_for_realm(settings: Settings, realm: str) -> str:
    """Public dashboard base URL (scheme + host, no trailing slash) for a resolved realm."""
    if realm == _REALM_INTERNAL:
        base = settings.dashboard_public_base_url_internal.strip()
    else:
        base = settings.dashboard_public_base_url_eastlake.strip()
    if not base:
        raise RequestRealmError()
    return base.rstrip("/")


def build_callback_url(base_url: str, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base_url.rstrip('/')}{normalized_path}"


def resolve_sso_redirect_uri(settings: Settings, realm: str | None) -> str:
    """WorkOS AuthKit callback URL for the request realm."""
    resolved = normalized_request_realm(settings, realm)
    return build_callback_url(
        public_base_url_for_realm(settings, resolved),
        WORKOS_SSO_CALLBACK_PATH,
    )


def resolve_ninjaone_redirect_uri(settings: Settings, realm: str | None) -> str:
    """NinjaOne OAuth callback URL for the request realm."""
    resolved = normalized_request_realm(settings, realm)
    return build_callback_url(
        public_base_url_for_realm(settings, resolved),
        settings.ninjaone_oauth_redirect_path,
    )
