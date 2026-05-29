# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import structlog
from workos import WorkOSClient

from src.config import Settings
from src.workos.portal_validation import validate_portal_client_id, validate_portal_email

log = structlog.get_logger()


def _format_created_at(value: datetime | str | None) -> str:
    """Format like WorkOS dashboard: May 29, 2026 7:09 AM."""
    if value is None:
        return ""
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            value = datetime.fromisoformat(normalized)
        except ValueError:
            return value
    hour = value.strftime("%I").lstrip("0") or "12"
    return f"{value.strftime('%b %d, %Y')} {hour}:{value.strftime('%M %p')}"


def _created_at_fields(value: datetime | str | None) -> tuple[str, str]:
    if value is None:
        return "", ""
    if isinstance(value, str):
        iso = value
        label = _format_created_at(value)
    else:
        iso = value.isoformat()
        label = _format_created_at(value)
    return iso, label


@dataclass(frozen=True)
class PortalUserRow:
    id: str
    email: str
    first_name: str
    last_name: str
    client_id: str
    membership: str = "active"  # active | pending
    created_at_iso: str = ""
    created_at_label: str = ""


class PortalUsersService:
    """User Management operations for the customer portal WorkOS organization."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        api_key = settings.customer_portal_api_key
        self._client = WorkOSClient(api_key=api_key)

    @property
    def organization_id(self) -> str:
        return self._settings.workos_customer_portal_organization_id.strip()

    @property
    def client_id_metadata_key(self) -> str:
        key = self._settings.workos_customer_portal_user_client_id_metadata_key.strip()
        return key or "client_id"

    def list_users(self, *, limit: int = 100) -> list[PortalUserRow]:
        org_id = self.organization_id
        if not org_id:
            return []

        metadata_key = self.client_id_metadata_key
        by_email: dict[str, PortalUserRow] = {}

        page = self._client.user_management.list_users(
            organization_id=org_id,
            limit=min(limit, 100),
            order="desc",
        )
        for user in page.auto_paging_iter():
            row = self._row_from_user(user, metadata_key=metadata_key, membership="active")
            by_email[row.email.lower()] = row
            if len(by_email) >= limit:
                return list(by_email.values())

        inv_page = self._client.user_management.list_invitations(
            organization_id=org_id,
            limit=min(limit, 100),
            order="desc",
        )
        for invitation in inv_page.auto_paging_iter():
            state = str(getattr(invitation.state, "value", invitation.state))
            if state != "pending":
                continue
            email = (invitation.email or "").strip()
            if not email:
                continue
            key = email.lower()
            if key in by_email:
                continue
            user = self._find_user_by_email(email)
            invite_created = getattr(invitation, "created_at", None)
            if user:
                row = self._row_from_user(
                    user,
                    metadata_key=metadata_key,
                    membership="pending",
                    created_at=invite_created,
                )
            else:
                created_iso, created_label = _created_at_fields(invite_created)
                row = PortalUserRow(
                    id=invitation.id,
                    email=email,
                    first_name="",
                    last_name="",
                    client_id="",
                    membership="pending",
                    created_at_iso=created_iso,
                    created_at_label=created_label,
                )
            by_email[key] = row
            if len(by_email) >= limit:
                break

        return list(by_email.values())

    def invite_user(self, *, email: str, client_id: str) -> PortalUserRow:
        """Invite a user to the portal org and set client_id user metadata."""
        org_id = self.organization_id
        if not org_id:
            raise ValueError("WORKOS_CUSTOMER_PORTAL_ORGANIZATION_ID is not configured")

        email = validate_portal_email(email)
        client_id = validate_portal_client_id(client_id)

        role_slug = self._settings.customer_portal_invite_role_slug
        if not role_slug:
            raise ValueError(
                "WORKOS_CUSTOMER_PORTAL_INVITE_ROLE_SLUG is not configured"
            )

        metadata_key = self.client_id_metadata_key
        metadata = {metadata_key: client_id}

        self._client.user_management.send_invitation(
            email=email,
            organization_id=org_id,
            role_slug=role_slug,
        )

        user = self._find_user_by_email(email)
        if user:
            merged = dict(user.metadata or {})
            merged.update(metadata)
            user = self._client.user_management.update_user(
                user.id,
                metadata=merged,
            )
        else:
            user = self._client.user_management.create_user(
                email=email,
                metadata=metadata,
            )

        log.info(
            "portal_user_invited",
            user_id=user.id,
            email=email,
            organization_id=org_id,
            role_slug=role_slug,
            metadata_key=metadata_key,
        )
        return self._row_from_user(user, metadata_key=metadata_key, membership="pending")

    def _find_user_by_email(self, email: str):
        page = self._client.user_management.list_users(email=email, limit=1)
        for user in page.data:
            if (user.email or "").strip().lower() == email.lower():
                return user
        return None

    def _row_from_user(
        self,
        user,
        *,
        metadata_key: str,
        membership: str = "active",
        created_at: datetime | str | None = None,
    ) -> PortalUserRow:
        metadata = user.metadata or {}
        created_iso, created_label = _created_at_fields(
            created_at if created_at is not None else getattr(user, "created_at", None)
        )
        return PortalUserRow(
            id=user.id,
            email=user.email or "",
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            client_id=metadata.get(metadata_key, ""),
            membership=membership,
            created_at_iso=created_iso,
            created_at_label=created_label,
        )
