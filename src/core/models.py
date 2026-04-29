# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class SyncAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DEACTIVATED = "deactivated"
    SKIPPED = "skipped"
    NO_CHANGE = "no_change"
    ROLE_ASSIGNED = "role_assigned"
    NOT_FOUND_SKIPPED = "not_found_skipped"
    ALREADY_INACTIVE = "already_inactive"
    ERROR = "error"


class RunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    ERROR = "error"
    NO_EVENTS = "no_events"


class HandlerResult(BaseModel):
    event_id: str
    event_type: str
    action: SyncAction
    target_adapter: str
    email: str | None = None
    target_user_id: str | None = None
    changed_fields: list[str] | None = None
    role: str | None = None
    error_message: str | None = None
    duration_ms: int = 0


class RunError(BaseModel):
    event_id: str
    event_type: str
    error_message: str
    traceback: str | None = None


class RunRecord(BaseModel):
    run_id: str
    adapter: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    status: RunStatus
    trigger_source: str  # "api" | "dashboard" | "scheduler"
    events_fetched: int
    events_processed: int
    cursor_before: str | None
    cursor_after: str | None
    results: list[HandlerResult]
    errors: list[RunError]

    @property
    def counts(self) -> dict[str, int]:
        """Returns count of each SyncAction across results."""
        totals: dict[str, int] = {action.value: 0 for action in SyncAction}
        for result in self.results:
            totals[result.action.value] = totals.get(result.action.value, 0) + 1
        return totals
