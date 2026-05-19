# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import structlog

from src.adapters.base import BaseTargetAdapter
from src.core.models import HandlerResult, SyncAction
from src.handlers.base import BaseEventHandler

log = structlog.get_logger()


class EventRouter:
    def __init__(self, handlers: list[BaseEventHandler]) -> None:
        self._handlers = handlers

    @staticmethod
    def _event_email(event: dict) -> str | None:
        data = event.get("data", {})
        if not isinstance(data, dict):
            return None
        user_data = data.get("user")
        if isinstance(user_data, dict):
            email = user_data.get("email")
            if isinstance(email, str) and email:
                return email
        email = data.get("email")
        if isinstance(email, str) and email:
            return email
        return None

    def route(self, event: dict, adapter: BaseTargetAdapter) -> HandlerResult:
        """
        Dispatches to the first handler that claims the event type.
        Returns SKIPPED if no handler matches.
        Returns ERROR on exception — never propagates.
        """
        event_type = event.get("event", "")
        event_id = event.get("id", "")

        for handler in self._handlers:
            if handler.can_handle(event_type):
                try:
                    return handler.handle(event, adapter)
                except Exception as exc:
                    log.error(
                        "handler_error",
                        event_id=event_id,
                        event_type=event_type,
                        error=str(exc),
                        exc_info=True,
                    )
                    return HandlerResult(
                        event_id=event_id,
                        event_type=event_type,
                        action=SyncAction.ERROR,
                        target_adapter=adapter.adapter_key,
                        email=self._event_email(event),
                        error_message=str(exc),
                    )

        log.debug("no_handler_for_event", event_id=event_id, event_type=event_type)
        return HandlerResult(
            event_id=event_id,
            event_type=event_type,
            action=SyncAction.SKIPPED,
            target_adapter=adapter.adapter_key,
        )
