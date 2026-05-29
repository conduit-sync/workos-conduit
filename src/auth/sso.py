# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import structlog

from src.auth.directory_access import (
    directory_user_role_slugs,
    find_directory_user_by_email,
)
from src.auth.menu_access import login_allowed_roles
from src.config import Settings
from workos import WorkOSClient

log = structlog.get_logger()


class SSOAccessDeniedError(Exception):
    def __init__(self, reason: str, *, detail: str | None = None) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(detail or reason)


class WorkOSSSOService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = WorkOSClient(
            api_key=settings.workos_api_key,
            client_id=settings.workos_sso_client_id,
        )

    def get_authorization_url(self, state: str) -> str:
        return self._client.user_management.get_authorization_url(
            redirect_uri=self._settings.workos_sso_redirect_uri,
            state=state,
            organization_id=self._settings.workos_sso_organization_id or None,
        )

    def exchange_code(self, code: str) -> dict:
        result = self._client.user_management.authenticate_with_code(code=code)
        user = result.user

        directory_roles = self._load_directory_roles(user.email)
        self._validate_login_roles(directory_roles)

        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "directory_roles": sorted(directory_roles),
        }

    def _load_directory_roles(self, email: str | None) -> set[str]:
        if not email:
            raise SSOAccessDeniedError("directory_user_not_found")

        directory_id = self._settings.workos_directory_id
        try:
            directory_user = find_directory_user_by_email(
                self._client,
                directory_id=directory_id,
                email=email,
            )
        except Exception as exc:
            log.warning(
                "sso_directory_lookup_failed",
                email=email,
                directory_id=directory_id,
                error=str(exc),
            )
            raise SSOAccessDeniedError("role_lookup_failed") from exc

        if not directory_user:
            log.warning(
                "sso_directory_user_not_found",
                email=email,
                directory_id=directory_id,
            )
            raise SSOAccessDeniedError("directory_user_not_found")

        return directory_user_role_slugs(directory_user)

    def _validate_login_roles(self, directory_roles: set[str]) -> None:
        allowed = login_allowed_roles(self._settings)
        if not allowed:
            return

        if not directory_roles.intersection(allowed):
            log.warning(
                "sso_directory_role_denied",
                user_roles=sorted(directory_roles),
                allowed_roles=sorted(allowed),
            )
            raise SSOAccessDeniedError(
                "directory_role_not_authorized",
                detail=(
                    f"Directory roles {sorted(directory_roles)!r} "
                    f"not in allowed {sorted(allowed)!r}"
                ),
            )
