# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from src.adapters.base import BaseTargetAdapter
from src.core.models import HandlerResult
from src.handlers.base import BaseEventHandler


class UserCreatedHandler(BaseEventHandler):
    def can_handle(self, event_type: str) -> bool:
        return event_type == "dsync.user.created"

    def handle(self, event: dict, adapter: BaseTargetAdapter) -> HandlerResult:
        user = self._workos_event_to_user(event["data"])
        result = adapter.provision_user_created(user)
        result.event_id = event["id"]
        result.event_type = event["event"]
        return result
