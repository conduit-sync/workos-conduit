# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import structlog

from src.adapters.base import BaseTargetAdapter, ProvisioningGroup
from src.core.models import HandlerResult
from src.handlers.base import BaseEventHandler

log = structlog.get_logger()


class GroupMembershipHandler(BaseEventHandler):
    def can_handle(self, event_type: str) -> bool:
        return event_type in ("dsync.group.user_added", "dsync.group.user_removed")

    def handle(self, event: dict, adapter: BaseTargetAdapter) -> HandlerResult:
        data = event["data"]
        group_name = data["group"]["name"]
        email = data["user"]["email"]
        action = "added" if event["event"] == "dsync.group.user_added" else "removed"

        log.debug(
            "handling_group_membership",
            event_id=event["id"],
            group=group_name,
            email=email,
            action=action,
        )

        user = self._workos_event_to_user(data["user"])
        group = ProvisioningGroup(user=user, group_name=group_name, action=action)
        result = adapter.provision_group_membership(group)
        result.event_id = event["id"]
        result.event_type = event["event"]
        log.info(
            "group_membership_handled",
            event_id=event["id"],
            group=group_name,
            email=email,
            action=action,
            result_action=result.action.value,
            duration_ms=result.duration_ms,
        )
        return result
