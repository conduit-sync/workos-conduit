# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import structlog

from src.adapters.base import BaseTargetAdapter
from src.backends.base import CursorBackend, StateBackend
from src.config import Settings
from src.core.event_router import EventRouter
from src.core.models import RunRecord, SyncAction
from src.core.sync_run import SyncRunContext
from src.workos.client import WorkOSEventsClient

log = structlog.get_logger()


class SyncEngine:
    def __init__(
        self,
        workos_client: WorkOSEventsClient,
        adapter: BaseTargetAdapter,
        cursor_backend: CursorBackend,
        state_backend: StateBackend,
        event_router: EventRouter,
        settings: Settings,
    ) -> None:
        self._workos = workos_client
        self._adapter = adapter
        self._cursor = cursor_backend
        self._state = state_backend
        self._router = event_router
        self._settings = settings

    def run_cycle(self, trigger_source: str = "api") -> RunRecord:
        ctx = SyncRunContext.start(
            adapter_key=self._adapter.adapter_key,
            trigger_source=trigger_source,
            cursor_before=self._cursor.get(),
        )

        log.info("sync_triggered", run_id=ctx.run_id, trigger_source=trigger_source)

        events, _ = self._workos.list_events(after=ctx.cursor_before)
        ctx.record_fetched(len(events))

        for event in events:
            result = self._router.route(event, self._adapter)
            ctx.record_result(result)

            if result.action == SyncAction.ERROR:
                if self._settings.sync_stop_on_error:
                    ctx.record_error(
                        event,
                        Exception(result.error_message or "handler error"),
                        terminated=True,
                    )
                    break
                # sync_stop_on_error=False: record but continue; do NOT advance cursor for this event
                ctx.record_error(
                    event,
                    Exception(result.error_message or "handler error"),
                    terminated=False,
                )
                continue

            self._cursor.save(event["id"])
            ctx.advance_cursor(event["id"])

            log.debug(
                "event_processed",
                event_id=event["id"],
                event_type=event.get("event"),
                action=result.action,
                email=result.email,
                duration_ms=result.duration_ms,
            )

        record = ctx.finalize()
        self._state.write_run(record)

        log.info(
            "cycle_complete",
            run_id=record.run_id,
            status=record.status,
            events_processed=record.events_processed,
            duration_seconds=record.duration_seconds,
        )
        return record
