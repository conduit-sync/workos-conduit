from __future__ import annotations

import uuid

from src.core.models import HandlerResult, RunStatus, SyncAction
from src.core.sync_run import SyncRunContext


def _result(action: SyncAction) -> HandlerResult:
    return HandlerResult(
        event_id="evt_001",
        event_type="dsync.user.created",
        action=action,
        target_adapter="ninjaone",
        email="alice@example.com",
    )


def test_start_populates_run_id_and_cursor_before():
    ctx = SyncRunContext.start("ninjaone", "api", "cursor_abc")
    assert uuid.UUID(ctx.run_id)  # valid UUID
    assert ctx.cursor_before == "cursor_abc"


def test_start_none_cursor():
    ctx = SyncRunContext.start("ninjaone", "api", None)
    assert ctx.cursor_before is None


def test_has_errors_false_without_error():
    ctx = SyncRunContext.start("ninjaone", "api", None)
    ctx.record_result(_result(SyncAction.CREATED))
    assert ctx.has_errors() is False


def test_has_errors_true_with_error():
    ctx = SyncRunContext.start("ninjaone", "api", None)
    ctx.record_result(_result(SyncAction.ERROR))
    assert ctx.has_errors() is True


def test_finalize_no_events_returns_no_events_status():
    ctx = SyncRunContext.start("ninjaone", "api", None)
    ctx.record_fetched(0)
    record = ctx.finalize()
    assert record.status == RunStatus.NO_EVENTS
    assert record.events_fetched == 0


def test_finalize_all_success():
    ctx = SyncRunContext.start("ninjaone", "api", None)
    ctx.record_fetched(2)
    ctx.record_result(_result(SyncAction.CREATED))
    ctx.record_result(_result(SyncAction.UPDATED))
    record = ctx.finalize()
    assert record.status == RunStatus.SUCCESS


def test_finalize_partial_failure_mid_stream():
    ctx = SyncRunContext.start("ninjaone", "api", None)
    ctx.record_fetched(3)
    ctx.record_result(_result(SyncAction.CREATED))
    ctx.record_result(_result(SyncAction.ERROR))
    record = ctx.finalize()
    assert record.status == RunStatus.PARTIAL_FAILURE


def test_finalize_error_status_when_terminated_early():
    ctx = SyncRunContext.start("ninjaone", "api", None)
    ctx.record_fetched(1)
    ctx.record_result(_result(SyncAction.ERROR))
    ctx.record_error(
        {"id": "evt_001", "event": "dsync.user.created"}, Exception("oops")
    )
    record = ctx.finalize()
    assert record.status == RunStatus.ERROR


def test_finalize_sets_finished_at_and_duration():
    ctx = SyncRunContext.start("ninjaone", "api", None)
    ctx.record_fetched(0)
    record = ctx.finalize()
    assert record.finished_at >= record.started_at
    assert record.duration_seconds >= 0


def test_advance_cursor_sets_cursor_after():
    ctx = SyncRunContext.start("ninjaone", "api", None)
    ctx.record_fetched(1)
    ctx.record_result(_result(SyncAction.CREATED))
    ctx.advance_cursor("evt_final")
    record = ctx.finalize()
    assert record.cursor_after == "evt_final"


def test_trigger_source_propagates():
    ctx = SyncRunContext.start("ninjaone", "dashboard", None)
    ctx.record_fetched(0)
    record = ctx.finalize()
    assert record.trigger_source == "dashboard"
