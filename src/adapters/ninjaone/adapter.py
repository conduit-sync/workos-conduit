# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from src.adapters.base import BaseTargetAdapter, ProvisioningGroup, ProvisioningUser
from src.adapters.ninjaone.client import NinjaOneAPIClient
from src.adapters.ninjaone.group_role_map import load_group_role_map
from src.adapters.ninjaone.mapper import (
    workos_group_to_ninjaone_role,
    workos_to_ninjaone,
)
from src.core.models import HandlerResult, SyncAction

if TYPE_CHECKING:
    from src.config import Settings

log = structlog.get_logger()

_EVT_USER_CREATED = "dsync.user.created"
_EVT_USER_UPDATED = "dsync.user.updated"
_EVT_USER_DELETED = "dsync.user.deleted"
_USERS_PATH = "/api/v2/users"


class NinjaOneAdapter(BaseTargetAdapter):
    adapter_key = "ninjaone"

    def __init__(self, settings: Settings) -> None:
        self._client = NinjaOneAPIClient(settings)
        self._role_map: dict[str, str] = load_group_role_map(settings)

    def provision_user_created(self, user: ProvisioningUser) -> HandlerResult:
        start = time.monotonic()
        existing = self._client.find_technician_by_email(user.email)
        if existing:
            return HandlerResult(
                event_id="",
                event_type=_EVT_USER_CREATED,
                action=SyncAction.SKIPPED,
                target_adapter=self.adapter_key,
                email=user.email,
                target_user_id=str(existing.get("id", "")),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        payload = workos_to_ninjaone(user)
        resp = self._client.create_technician(payload)
        return HandlerResult(
            event_id="",
            event_type=_EVT_USER_CREATED,
            action=SyncAction.CREATED,
            target_adapter=self.adapter_key,
            email=user.email,
            target_user_id=str(resp.get("id", "")),
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def provision_user_updated(self, user: ProvisioningUser) -> HandlerResult:
        start = time.monotonic()
        existing = self._client.find_technician_by_email(user.email)
        if not existing:
            result = self.provision_user_created(user)
            result.event_type = _EVT_USER_UPDATED
            return result

        diff: dict = {}
        if existing.get("firstName") != user.first_name:
            diff["firstName"] = user.first_name
        if existing.get("lastName") != user.last_name:
            diff["lastName"] = user.last_name
        if existing.get("enabled") != user.is_active:
            diff["enabled"] = user.is_active

        if not diff:
            return HandlerResult(
                event_id="",
                event_type=_EVT_USER_UPDATED,
                action=SyncAction.NO_CHANGE,
                target_adapter=self.adapter_key,
                email=user.email,
                target_user_id=str(existing.get("id", "")),
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        self._client.update_technician(existing["id"], diff)
        return HandlerResult(
            event_id="",
            event_type=_EVT_USER_UPDATED,
            action=SyncAction.UPDATED,
            target_adapter=self.adapter_key,
            email=user.email,
            target_user_id=str(existing.get("id", "")),
            changed_fields=list(diff.keys()),
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def provision_user_deactivated(self, user: ProvisioningUser) -> HandlerResult:
        start = time.monotonic()
        existing = self._client.find_technician_by_email(user.email)
        if not existing:
            return HandlerResult(
                event_id="",
                event_type=_EVT_USER_DELETED,
                action=SyncAction.NOT_FOUND_SKIPPED,
                target_adapter=self.adapter_key,
                email=user.email,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        if not existing.get("enabled", True):
            return HandlerResult(
                event_id="",
                event_type=_EVT_USER_DELETED,
                action=SyncAction.ALREADY_INACTIVE,
                target_adapter=self.adapter_key,
                email=user.email,
                target_user_id=str(existing.get("id", "")),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        self._client.deactivate_technician(existing["id"])
        return HandlerResult(
            event_id="",
            event_type=_EVT_USER_DELETED,
            action=SyncAction.DEACTIVATED,
            target_adapter=self.adapter_key,
            email=user.email,
            target_user_id=str(existing.get("id", "")),
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def provision_group_membership(self, group: ProvisioningGroup) -> HandlerResult:
        start = time.monotonic()
        role = workos_group_to_ninjaone_role(group.group_name, self._role_map)
        if role is None:
            log.debug(
                "group_role_mapping_not_found",
                group=group.group_name,
                email=group.user.email,
            )
            return HandlerResult(
                event_id="",
                event_type=f"dsync.group.user_{group.action}",
                action=SyncAction.SKIPPED,
                target_adapter=self.adapter_key,
                email=group.user.email,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        existing = self._client.find_technician_by_email(group.user.email)
        if not existing:
            return HandlerResult(
                event_id="",
                event_type=f"dsync.group.user_{group.action}",
                action=SyncAction.NOT_FOUND_SKIPPED,
                target_adapter=self.adapter_key,
                email=group.user.email,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        self._client.update_technician(existing["id"], {"role": role})
        return HandlerResult(
            event_id="",
            event_type=f"dsync.group.user_{group.action}",
            action=SyncAction.ROLE_ASSIGNED,
            target_adapter=self.adapter_key,
            email=group.user.email,
            target_user_id=str(existing.get("id", "")),
            role=role,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def health_check(self) -> bool:
        return self._client.health_check()
