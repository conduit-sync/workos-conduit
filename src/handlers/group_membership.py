# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from src.adapters.base import BaseTargetAdapter, ProvisioningGroup
from src.config import get_settings
from src.core.allowed_groups import load_allowed_groups
from src.core.models import HandlerResult, SyncAction
from src.handlers.base import BaseEventHandler


class GroupMembershipHandler(BaseEventHandler):
    def can_handle(self, event_type: str) -> bool:
        return event_type in ("dsync.group.user_added", "dsync.group.user_removed")

    def handle(self, event: dict, adapter: BaseTargetAdapter) -> HandlerResult:
        data = event["data"]
        group_name = data["group"]["name"]
        action = "added" if event["event"] == "dsync.group.user_added" else "removed"

        allowed = load_allowed_groups(get_settings())
        if allowed and group_name not in allowed:
            return HandlerResult(
                event_id=event["id"],
                event_type=event["event"],
                action=SyncAction.SKIPPED,
                target_adapter=adapter.adapter_key,
                email=data["user"]["email"],
            )

        user = self._workos_event_to_user(data["user"])
        group = ProvisioningGroup(user=user, group_name=group_name, action=action)
        result = adapter.provision_group_membership(group)
        result.event_id = event["id"]
        result.event_type = event["event"]
        return result
