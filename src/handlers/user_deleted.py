# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from src.adapters.base import BaseTargetAdapter, ProvisioningUser
from src.core.models import HandlerResult
from src.handlers.base import BaseEventHandler


class UserDeletedHandler(BaseEventHandler):
    def can_handle(self, event_type: str) -> bool:
        return event_type == "dsync.user.deleted"

    def handle(self, event: dict, adapter: BaseTargetAdapter) -> HandlerResult:
        data = event["data"]
        # Deleted users are always inactive
        user = ProvisioningUser(
            email=data["email"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            is_active=False,
            department=(data.get("custom_attributes") or {}).get("department"),
            job_title=(data.get("custom_attributes") or {}).get("job_title"),
            external_id=data["id"],
        )
        result = adapter.provision_user_deactivated(user)
        result.event_id = event["id"]
        result.event_type = event["event"]
        return result
