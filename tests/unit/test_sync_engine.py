from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from src.core.models import HandlerResult, RunStatus, SyncAction
from src.core.sync_engine import SyncEngine


def _make_result(action: SyncAction, event_id: str = "evt_001") -> HandlerResult:
    return HandlerResult(
        event_id=event_id,
        event_type="dsync.user.created",
        action=action,
        target_adapter="ninjaone",
        email="alice@example.com",
    )


def _make_event(event_id: str) -> dict:
    return {
        "id": event_id,
        "event": "dsync.user.created",
        "data": {
            "id": "dir_user_001",
            "email": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Smith",
            "state": "active",
            "custom_attributes": {},
        },
    }


def _make_engine(
    events: list[dict],
    router_results: list[HandlerResult],
    stop_on_error: bool = True,
) -> SyncEngine:
    settings = MagicMock()
    settings.sync_stop_on_error = stop_on_error
    settings.sync_target_adapter = "ninjaone"

    workos_client = MagicMock()
    workos_client.list_events.return_value = (events, None)

    adapter = MagicMock()
    adapter.adapter_key = "ninjaone"

    cursor_backend = MagicMock()
    cursor_backend.get.return_value = None

    state_backend = MagicMock()

    router = MagicMock()
    router.route.side_effect = router_results

    return (
        SyncEngine(
            workos_client=workos_client,
            adapter=adapter,
            cursor_backend=cursor_backend,
            state_backend=state_backend,
            event_router=router,
            settings=settings,
        ),
        state_backend,
        cursor_backend,
        router,
    )


@pytest.fixture
def make_engine():
    return _make_engine


def test_no_events_returns_no_events_status():
    engine, state_backend, cursor_backend, _ = _make_engine([], [])
    record = engine.run_cycle()
    assert record.status == RunStatus.NO_EVENTS
    assert record.events_fetched == 0
    state_backend.write_run.assert_called_once()


def test_all_success_saves_cursor_three_times():
    events = [_make_event(f"evt_{i}") for i in range(3)]
    results = [_make_result(SyncAction.CREATED, f"evt_{i}") for i in range(3)]
    engine, _, cursor_backend, _ = _make_engine(events, results)
    record = engine.run_cycle()
    assert record.status == RunStatus.SUCCESS
    assert cursor_backend.save.call_count == 3
    cursor_backend.save.assert_has_calls([call("evt_0"), call("evt_1"), call("evt_2")])


def test_error_at_event2_stop_on_error_true_breaks_loop():
    events = [_make_event(f"evt_{i}") for i in range(3)]
    results = [
        _make_result(SyncAction.CREATED, "evt_0"),
        _make_result(SyncAction.ERROR, "evt_1"),
        _make_result(SyncAction.CREATED, "evt_2"),
    ]
    engine, state_backend, cursor_backend, router = _make_engine(
        events, results, stop_on_error=True
    )
    record = engine.run_cycle()
    assert record.status in (RunStatus.PARTIAL_FAILURE, RunStatus.ERROR)
    # cursor saved only for evt_0
    assert cursor_backend.save.call_count == 1
    # router called for evt_0 and evt_1, then stopped
    assert router.route.call_count == 2
    state_backend.write_run.assert_called_once()


def test_error_at_event2_stop_on_error_false_continues():
    events = [_make_event(f"evt_{i}") for i in range(3)]
    results = [
        _make_result(SyncAction.CREATED, "evt_0"),
        _make_result(SyncAction.ERROR, "evt_1"),
        _make_result(SyncAction.CREATED, "evt_2"),
    ]
    engine, _, cursor_backend, router = _make_engine(
        events, results, stop_on_error=False
    )
    record = engine.run_cycle()
    assert record.status == RunStatus.PARTIAL_FAILURE
    assert router.route.call_count == 3
    # cursor saved for evt_0 and evt_2 (not evt_1)
    assert cursor_backend.save.call_count == 2


def test_state_writer_called_exactly_once():
    events = [_make_event("evt_0")]
    results = [_make_result(SyncAction.CREATED, "evt_0")]
    engine, state_backend, _, _ = _make_engine(events, results)
    engine.run_cycle()
    state_backend.write_run.assert_called_once()


def test_trigger_source_propagates():
    engine, _, _, _ = _make_engine([], [])
    record = engine.run_cycle(trigger_source="dashboard")
    assert record.trigger_source == "dashboard"
