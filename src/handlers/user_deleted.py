# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import structlog

from src.adapters.base import BaseTargetAdapter
from src.core.models import HandlerResult
from src.handlers.base import BaseEventHandler

log = structlog.get_logger()


class UserDeletedHandler(BaseEventHandler):
    def can_handle(self, event_type: str) -> bool:
        return event_type == "dsync.user.deleted"

    def handle(self, event: dict, adapter: BaseTargetAdapter) -> HandlerResult:
        user = self._workos_event_to_user(event["data"])
        user = user.model_copy(update={"is_active": False})
        log.debug("handling_user_deleted", event_id=event["id"], email=user.email)
        result = adapter.provision_user_deactivated(user)
        result.event_id = event["id"]
        result.event_type = event["event"]
        log.info(
            "user_deleted_handled",
            event_id=event["id"],
            email=user.email,
            action=result.action.value,
            duration_ms=result.duration_ms,
        )
        return result
