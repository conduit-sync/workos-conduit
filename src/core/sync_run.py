# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import traceback
import uuid
from datetime import UTC, datetime

from src.core.models import HandlerResult, RunError, RunRecord, RunStatus, SyncAction


class SyncRunContext:
    """
    Unit of Work for a single run_cycle execution.

    Owns all mutable run state so SyncEngine stays a thin orchestrator.
    """

    def __init__(
        self,
        run_id: str,
        adapter_key: str,
        trigger_source: str,
        cursor_before: str | None,
        started_at: datetime,
    ) -> None:
        self._run_id = run_id
        self._adapter_key = adapter_key
        self._trigger_source = trigger_source
        self._cursor_before = cursor_before
        self._cursor_after: str | None = None
        self._started_at = started_at
        self._events_fetched: int = 0
        self._results: list[HandlerResult] = []
        self._errors: list[RunError] = []
        self._terminated_early: bool = False

    @classmethod
    def start(
        cls,
        adapter_key: str,
        trigger_source: str,
        cursor_before: str | None,
    ) -> SyncRunContext:
        return cls(
            run_id=str(uuid.uuid4()),
            adapter_key=adapter_key,
            trigger_source=trigger_source,
            cursor_before=cursor_before,
            started_at=datetime.now(tz=UTC),
        )

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def cursor_before(self) -> str | None:
        return self._cursor_before

    def record_fetched(self, count: int) -> None:
        self._events_fetched = count

    def record_result(self, result: HandlerResult) -> None:
        self._results.append(result)

    def record_error(
        self, event: dict, exc: Exception, terminated: bool = True
    ) -> None:
        tb = traceback.format_exc()
        self._errors.append(
            RunError(
                event_id=event.get("id", ""),
                event_type=event.get("event", ""),
                error_message=str(exc),
                traceback=tb,
            )
        )
        if terminated:
            self._terminated_early = True

    def advance_cursor(self, event_id: str) -> None:
        self._cursor_after = event_id

    def has_errors(self) -> bool:
        return any(r.action == SyncAction.ERROR for r in self._results)

    def finalize(self) -> RunRecord:
        finished_at = datetime.now(tz=UTC)
        duration = (finished_at - self._started_at).total_seconds()

        events_processed = sum(
            1 for r in self._results if r.action != SyncAction.SKIPPED
        )

        if self._events_fetched == 0:
            status = RunStatus.NO_EVENTS
        elif self._terminated_early:
            status = RunStatus.ERROR
        elif self.has_errors():
            status = RunStatus.PARTIAL_FAILURE
        else:
            status = RunStatus.SUCCESS

        return RunRecord(
            run_id=self._run_id,
            adapter=self._adapter_key,
            started_at=self._started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            status=status,
            trigger_source=self._trigger_source,
            events_fetched=self._events_fetched,
            events_processed=events_processed,
            cursor_before=self._cursor_before,
            cursor_after=self._cursor_after,
            results=self._results,
            errors=self._errors,
        )
