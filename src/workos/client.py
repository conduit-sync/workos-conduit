# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

import workos

if TYPE_CHECKING:
    from src.config import Settings

log = structlog.get_logger()

_DEFAULT_EVENT_TYPES = [
    "dsync.user.created",
    "dsync.user.updated",
    "dsync.user.deleted",
    "dsync.group.user_added",
    "dsync.group.user_removed",
]


def _parse_event_types(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return _DEFAULT_EVENT_TYPES
    if raw.startswith("["):
        return json.loads(raw)
    return [t.strip() for t in raw.split(",") if t.strip()]


class WorkOSEventsClient:
    def __init__(self, settings: Settings) -> None:
        self._client = workos.WorkOSClient(api_key=settings.workos_api_key)
        self._types = _parse_event_types(settings.workos_event_types)
        self._page_size = settings.workos_events_page_size

    def list_events(self, after: str | None = None) -> tuple[list[dict], str | None]:
        """
        Fetches Directory Sync events from WorkOS.
        Returns (events_list, last_event_id).
        last_event_id is the ID of the final event, used to advance the cursor.
        """
        kwargs: dict = {
            "events": self._types,
            "limit": self._page_size,
        }
        if after:
            kwargs["after"] = after

        response = self._client.events.list_events(**kwargs)

        # The SDK returns a ListResponse — normalise to list[dict]
        if hasattr(response, "data"):
            events = [
                e.__dict__ if hasattr(e, "__dict__") else dict(e) for e in response.data
            ]
        elif hasattr(response, "__iter__"):
            events = list(response)
        else:
            events = []

        last_event_id = events[-1]["id"] if events else None
        log.debug("workos_events_fetched", count=len(events), after=after)
        return events, last_event_id
