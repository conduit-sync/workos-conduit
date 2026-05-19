# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import structlog

from src.adapters.base import BaseTargetAdapter
from src.backends.base import CursorBackend, StateBackend
from src.config import Settings
from src.core.event_router import EventRouter
from src.core.models import HandlerResult, RunRecord, SyncAction
from src.core.sync_run import SyncRunContext
from src.workos.client import WorkOSEventsClient

_USER_CREATED_UPDATED = {"dsync.user.created", "dsync.user.updated"}
_GROUP_MEMBERSHIP = {"dsync.group.user_added", "dsync.group.user_removed"}
_USER_EVENTS_WITH_GROUP_LOOKUP = _USER_CREATED_UPDATED | _GROUP_MEMBERSHIP

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

    def _skipped_result(
        self, event: dict, event_type: str, email: str
    ) -> HandlerResult:
        return HandlerResult(
            event_id=event["id"],
            event_type=event_type,
            action=SyncAction.SKIPPED,
            target_adapter=self._adapter.adapter_key,
            email=email,
        )

    def _prefetch_group_memberships(
        self,
        events: list[dict],
        group_cache: dict[str, list[str]],
    ) -> None:
        """Batch-fetch WorkOS group memberships for all users in user events.

        Runs all WorkOS group queries upfront before any NinjaOne API calls
        so the two I/O phases are cleanly separated.
        """
        user_ids = {
            self._event_user_id(event)
            for event in events
            if event.get("event", "") in _USER_EVENTS_WITH_GROUP_LOOKUP
            and self._event_user_id(event)
        }
        for user_id in user_ids:
            group_cache[user_id] = self._workos.get_user_group_names(user_id)
        if user_ids:
            log.debug("workos_group_memberships_prefetched", user_count=len(user_ids))

    def _classify_event(
        self,
        event: dict,
        watched_groups: set[str],
        admin_group: str,
        group_cache: dict[str, list[str]],
    ) -> str:
        """Return 'admin', 'unmatched', or 'pending' for a single event."""
        event_type = event.get("event", "")
        if event_type not in _USER_EVENTS_WITH_GROUP_LOOKUP or not (
            admin_group or watched_groups
        ):
            return "pending"
        user_groups = group_cache.get(self._event_user_id(event), [])
        if admin_group and admin_group in user_groups:
            return "admin"
        if event_type in _USER_CREATED_UPDATED and watched_groups and not any(
            g in watched_groups for g in user_groups
        ):
            return "unmatched"
        return "pending"

    @staticmethod
    def _event_email(event: dict) -> str:
        data = event.get("data", {})
        # Group events nest email under data.user; user events have it at data.email
        return data.get("user", {}).get("email", "") or data.get("email", "")

    @staticmethod
    def _event_user_id(event: dict) -> str:
        data = event.get("data", {})
        # Group events may nest id under data.user.id; user events usually use data.id.
        return data.get("id", "") or data.get("user", {}).get("id", "")

    def _log_pending_events(
        self,
        events: list[dict],
        watched_groups: set[str],
        admin_group: str,
        group_cache: dict[str, list[str]],
    ) -> None:
        """Log a summary of what will be sent to NinjaOne before processing starts."""
        if not events:
            return

        pending: dict[str, list[str]] = {}
        skipped_admin: list[str] = []
        skipped_group: list[str] = []

        for event in events:
            email = self._event_email(event)
            classification = self._classify_event(
                event, watched_groups, admin_group, group_cache
            )
            if classification == "admin":
                skipped_admin.append(email)
            elif classification == "unmatched":
                skipped_group.append(email)
            else:
                pending.setdefault(event.get("event", ""), []).append(email)

        if pending:
            deduped = {k: sorted(set(v)) for k, v in pending.items()}
            log.info(
                "pending_ninjaone_operations",
                total=sum(len(v) for v in deduped.values()),
                by_event_type=deduped,
            )
        else:
            log.info("no_ninjaone_operations_pending", events_fetched=len(events))
        if skipped_admin:
            log.info(
                "users_skipped_admin_group",
                count=len(skipped_admin),
                emails=skipped_admin,
                admin_group=admin_group,
            )
        if skipped_group:
            log.info(
                "users_skipped_not_in_watched_group",
                count=len(skipped_group),
                emails=skipped_group,
            )

    def _should_skip_user_event(
        self,
        event: dict,
        event_type: str,
        watched_groups: set[str],
        admin_group: str,
        group_cache: dict[str, list[str]],
    ) -> str | None:
        """Return a skip reason string if the user event should be skipped, else None."""
        if event_type not in _USER_EVENTS_WITH_GROUP_LOOKUP or not (
            admin_group or watched_groups
        ):
            return None
        user_id = self._event_user_id(event)
        if user_id not in group_cache:
            group_cache[user_id] = self._workos.get_user_group_names(user_id)
        user_groups = group_cache[user_id]
        if admin_group and admin_group in user_groups:
            return "admin_group"
        if event_type in _USER_CREATED_UPDATED and watched_groups and not any(
            g in watched_groups for g in user_groups
        ):
            return "not_in_watched_group"
        return None

    def _process_event(
        self,
        event: dict,
        ctx: SyncRunContext,
        watched_groups: set[str],
        admin_group: str,
        group_cache: dict[str, list[str]],
    ) -> bool:
        """Process a single event. Returns False if the cycle should stop."""
        event_type = event.get("event", "")
        email = event.get("data", {}).get("email", "")

        skip_reason = self._should_skip_user_event(
            event, event_type, watched_groups, admin_group, group_cache
        )
        if skip_reason == "admin_group":
            log.info(
                "user_event_skipped_admin_group",
                event_id=event["id"],
                event_type=event_type,
                email=email,
                admin_group=admin_group,
            )
            ctx.record_result(self._skipped_result(event, event_type, email))
            self._cursor.save(event["id"])
            ctx.advance_cursor(event["id"])
            return True
        if skip_reason == "not_in_watched_group":
            user_id = self._event_user_id(event)
            log.debug(
                "user_event_skipped_not_in_watched_group",
                event_id=event["id"],
                event_type=event_type,
                email=email,
                user_groups=group_cache.get(user_id, []),
                watched_groups=sorted(watched_groups),
            )
            ctx.record_result(self._skipped_result(event, event_type, email))
            self._cursor.save(event["id"])
            ctx.advance_cursor(event["id"])
            return True

        result = self._router.route(event, self._adapter)
        ctx.record_result(result)

        if result.action == SyncAction.ERROR:
            if self._settings.sync_stop_on_error:
                ctx.record_error(
                    event,
                    RuntimeError(result.error_message or "handler error"),
                    terminated=True,
                )
                return False
            ctx.record_error(
                event,
                RuntimeError(result.error_message or "handler error"),
                terminated=False,
            )
            return True

        self._cursor.save(event["id"])
        ctx.advance_cursor(event["id"])
        log.debug(
            "event_processed",
            event_id=event["id"],
            event_type=event_type,
            action=result.action,
            email=result.email,
            duration_ms=result.duration_ms,
        )
        return True

    def run_cycle(self, trigger_source: str = "api") -> RunRecord:
        ctx = SyncRunContext.start(
            adapter_key=self._adapter.adapter_key,
            trigger_source=trigger_source,
            cursor_before=self._cursor.get(),
        )

        log.info("sync_triggered", run_id=ctx.run_id, trigger_source=trigger_source)

        events, _ = self._workos.list_events(after=ctx.cursor_before)
        ctx.record_fetched(len(events))
        log.info(
            "workos_events_fetched",
            run_id=ctx.run_id,
            count=len(events),
            cursor=ctx.cursor_before,
        )

        watched_groups = self._adapter.watched_groups()
        admin_group = self._settings.ninjaone_group_admins.strip()
        group_cache: dict[str, list[str]] = {}

        # Batch all WorkOS group lookups upfront before any NinjaOne calls
        if watched_groups or admin_group:
            self._prefetch_group_memberships(events, group_cache)

        self._log_pending_events(events, watched_groups, admin_group, group_cache)

        for event in events:
            if not self._process_event(
                event, ctx, watched_groups, admin_group, group_cache
            ):
                break

        record = ctx.finalize()
        self._state.write_run(record)

        log.info(
            "cycle_complete",
            run_id=record.run_id,
            status=record.status,
            events_processed=record.events_processed,
            duration_seconds=record.duration_seconds,
        )

        created_emails = [
            r.email
            for r in record.results
            if r.action == SyncAction.CREATED and r.email
        ]
        if created_emails:
            log.info(
                "users_created_in_cycle",
                run_id=record.run_id,
                count=len(created_emails),
                emails=created_emails,
            )

        return record
