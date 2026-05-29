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
        self._client = workos.WorkOSClient(api_key=settings.workos_sso_internal_org_api_key)
        self._types = _parse_event_types(settings.workos_event_types)
        self._page_size = settings.workos_events_page_size

    def list_events(self, after: str | None = None) -> tuple[list[dict], str | None]:
        """
        Fetches all Directory Sync events from WorkOS since the cursor position,
        paginating automatically until there are no more pages.

        Events are fetched in ascending order (oldest first) so the cursor
        advances correctly — processing event N before event N+1.

        Returns (events_list, last_event_id).
        """
        kwargs: dict = {
            "events": self._types,
            "limit": self._page_size,
            "order": "asc",
        }
        if after:
            kwargs["after"] = after

        first_page = self._client.events.list_events(**kwargs)

        events: list[dict] = []
        for event_obj in first_page.auto_paging_iter():
            events.append(
                event_obj.to_dict()
                if hasattr(event_obj, "to_dict")
                else event_obj.__dict__
            )

        last_event_id = events[-1]["id"] if events else None
        log.debug("workos_events_fetched", count=len(events), after=after)
        return events, last_event_id

    def get_user_group_names(self, user_id: str) -> list[str]:
        """Returns names of every directory group the user belongs to.

        Returns an empty list on any API error so the caller can decide
        how to handle it (log + skip vs. raise).
        """
        try:
            page = self._client.directory_sync.list_directory_groups(
                user=user_id, limit=100
            )
            names = [grp.name for grp in page.auto_paging_iter()]
            log.debug("workos_user_groups_fetched", user_id=user_id, groups=names)
            return names
        except Exception as exc:
            log.warning(
                "workos_get_user_groups_failed",
                user_id=user_id,
                error=str(exc),
            )
            return []
