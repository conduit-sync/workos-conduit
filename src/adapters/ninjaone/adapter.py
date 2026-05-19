# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

from src.adapters.base import BaseTargetAdapter, ProvisioningGroup, ProvisioningUser
from src.adapters.ninjaone.client import NinjaOneAPIClient, NinjaOneEmailAlreadyInUse
from src.adapters.ninjaone.group_role_map import OrgGroupMapping, load_group_role_map
from src.adapters.ninjaone.mapper import workos_to_ninjaone
from src.core.models import HandlerResult, SyncAction

if TYPE_CHECKING:
    from src.config import Settings

log = structlog.get_logger()

_SUPPORTED_ROLE = "END_USER"
_EVT_USER_CREATED = "dsync.user.created"
_EVT_USER_UPDATED = "dsync.user.updated"
_EVT_USER_DELETED = "dsync.user.deleted"


class NinjaOneAdapter(BaseTargetAdapter):
    adapter_key = "ninjaone"

    def __init__(self, settings: Settings) -> None:
        if not settings.ninjaone_oauth_client_id:
            raise ValueError(
                "ninjaone_oauth_client_id is required when sync_target_adapter=ninjaone"
            )
        if not settings.ninjaone_oauth_client_secret:
            raise ValueError(
                "ninjaone_oauth_client_secret is required when sync_target_adapter=ninjaone"
            )
        self._client = NinjaOneAPIClient(settings)
        self._role_map: dict[str, OrgGroupMapping] = load_group_role_map(settings)
        self._admin_group = settings.ninjaone_group_admins.strip()

    def _make_result(
        self,
        event_type: str,
        action: SyncAction,
        start: float,
        email: str,
        **kwargs: Any,
    ) -> HandlerResult:
        return HandlerResult(
            event_id="",
            event_type=event_type,
            action=action,
            target_adapter=self.adapter_key,
            email=email,
            duration_ms=int((time.monotonic() - start) * 1000),
            **kwargs,
        )

    def _build_user_diff(
        self,
        existing: dict,
        user: ProvisioningUser,
        expected_org_id: int | None = None,
    ) -> dict:
        diff: dict = {}
        if existing.get("firstName") != user.first_name:
            diff["firstName"] = user.first_name
        if existing.get("lastName") != user.last_name:
            diff["lastName"] = user.last_name
        if (
            expected_org_id is not None
            and existing.get("organizationId") != expected_org_id
        ):
            diff["organizationId"] = expected_org_id
        return diff

    def provision_user_created(
        self, user: ProvisioningUser, org_id: int | None = None
    ) -> HandlerResult:
        start = time.monotonic()
        existing = self._client.find_end_user_by_email(user.email)
        if existing:
            log.info(
                "user_already_exists_in_ninjaone",
                email=user.email,
                ninjaone_id=existing.get("id"),
            )
            return self._make_result(
                _EVT_USER_CREATED,
                SyncAction.SKIPPED,
                start,
                user.email,
                target_user_id=str(existing.get("id", "")),
            )
        payload = workos_to_ninjaone(user, org_id=org_id)
        log.info(
            "creating_end_user_in_ninjaone",
            email=user.email,
            org_id=org_id,
            payload=payload,
        )
        try:
            resp = self._client.create_end_user(payload)
        except NinjaOneEmailAlreadyInUse:
            log.info(
                "user_creation_skipped_email_already_in_use",
                email=user.email,
            )
            return self._make_result(
                _EVT_USER_CREATED,
                SyncAction.SKIPPED,
                start,
                user.email,
            )
        return self._make_result(
            _EVT_USER_CREATED,
            SyncAction.CREATED,
            start,
            user.email,
            target_user_id=str(resp.get("id", "")),
        )

    def provision_user_updated(self, user: ProvisioningUser) -> HandlerResult:
        start = time.monotonic()
        existing = self._client.find_end_user_by_email(user.email)
        if not existing:
            result = self.provision_user_created(user)
            result.event_type = _EVT_USER_UPDATED
            return result

        diff = self._build_user_diff(existing, user)
        if not diff:
            return self._make_result(
                _EVT_USER_UPDATED,
                SyncAction.NO_CHANGE,
                start,
                user.email,
                target_user_id=str(existing.get("id", "")),
            )

        self._client.update_end_user(existing["id"], diff)
        return self._make_result(
            _EVT_USER_UPDATED,
            SyncAction.UPDATED,
            start,
            user.email,
            target_user_id=str(existing.get("id", "")),
            changed_fields=list(diff.keys()),
        )

    def provision_user_deactivated(self, user: ProvisioningUser) -> HandlerResult:
        start = time.monotonic()
        existing = self._client.find_end_user_by_email(user.email)
        if not existing:
            return self._make_result(
                _EVT_USER_DELETED,
                SyncAction.NOT_FOUND_SKIPPED,
                start,
                user.email,
            )
        if not existing.get("enabled", True):
            return self._make_result(
                _EVT_USER_DELETED,
                SyncAction.ALREADY_INACTIVE,
                start,
                user.email,
                target_user_id=str(existing.get("id", "")),
            )
        self._client.deactivate_end_user(existing["id"])
        return self._make_result(
            _EVT_USER_DELETED,
            SyncAction.DEACTIVATED,
            start,
            user.email,
            target_user_id=str(existing.get("id", "")),
        )

    def provision_group_membership(self, group: ProvisioningGroup) -> HandlerResult:
        start = time.monotonic()
        evt = f"dsync.group.user_{group.action}"
        if self._admin_group and group.group_name == self._admin_group:
            log.info(
                "group_membership_skipped_admin_group",
                group=group.group_name,
                email=group.user.email,
            )
            return self._make_result(evt, SyncAction.SKIPPED, start, group.user.email)

        mapping = self._role_map.get(group.group_name)
        if mapping is None:
            log.info(
                "group_membership_skipped_no_role_mapping",
                group=group.group_name,
                email=group.user.email,
            )
            return self._make_result(evt, SyncAction.SKIPPED, start, group.user.email)

        if mapping.ninjaone_role.upper() != _SUPPORTED_ROLE:
            log.warning(
                "group_membership_skipped_unsupported_role",
                group=group.group_name,
                email=group.user.email,
                role=mapping.ninjaone_role,
                supported_role=_SUPPORTED_ROLE,
                reason="Only END_USER role is supported at this time",
            )
            return self._make_result(evt, SyncAction.SKIPPED, start, group.user.email)

        if group.action == "added":
            existing = self._client.find_end_user_by_email(group.user.email)
            if not existing:
                result = self.provision_user_created(
                    group.user, org_id=mapping.ninjaone_organization_id
                )
                result.event_type = evt
                return result

            diff = self._build_user_diff(
                existing, group.user, expected_org_id=mapping.ninjaone_organization_id
            )
            if diff:
                log.info(
                    "updating_end_user_in_ninjaone",
                    email=group.user.email,
                    changed_fields=list(diff.keys()),
                )
                self._client.update_end_user(existing["id"], diff)
                return self._make_result(
                    evt,
                    SyncAction.UPDATED,
                    start,
                    group.user.email,
                    target_user_id=str(existing.get("id", "")),
                    changed_fields=list(diff.keys()),
                )

            log.info(
                "user_already_exists_in_ninjaone",
                email=group.user.email,
                ninjaone_id=existing.get("id"),
            )
            return self._make_result(
                evt,
                SyncAction.SKIPPED,
                start,
                group.user.email,
                target_user_id=str(existing.get("id", "")),
            )

        # action == "removed"
        result = self.provision_user_deactivated(group.user)
        result.event_type = evt
        return result

    def watched_groups(self) -> set[str]:
        return set(self._role_map.keys())

    def health_check(self) -> bool:
        return self._client.health_check()
