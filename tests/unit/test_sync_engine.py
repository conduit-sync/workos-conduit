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


def _make_event(event_id: str, event_type: str = "dsync.user.created") -> dict:
    return {
        "id": event_id,
        "event": event_type,
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
    watched_groups: set[str] | None = None,
    user_groups: list[str] | None = None,
    admin_group: str = "",
) -> tuple:
    settings = MagicMock()
    settings.sync_stop_on_error = stop_on_error
    settings.sync_target_adapter = "ninjaone"
    settings.ninjaone_group_admins = admin_group

    workos_client = MagicMock()
    workos_client.list_events.return_value = (events, None)
    workos_client.get_user_group_names.return_value = user_groups or []

    adapter = MagicMock()
    adapter.adapter_key = "ninjaone"
    adapter.watched_groups.return_value = (
        watched_groups if watched_groups is not None else set()
    )

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
        workos_client,
    )


@pytest.fixture
def make_engine():
    return _make_engine


def test_no_events_returns_no_events_status():
    engine, state_backend, _, _, _ = _make_engine([], [])
    record = engine.run_cycle()
    assert record.status == RunStatus.NO_EVENTS
    assert record.events_fetched == 0
    state_backend.write_run.assert_called_once()


def test_all_success_saves_cursor_three_times():
    events = [_make_event(f"evt_{i}") for i in range(3)]
    results = [_make_result(SyncAction.CREATED, f"evt_{i}") for i in range(3)]
    engine, _, cursor_backend, _, _ = _make_engine(events, results)
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
    engine, state_backend, cursor_backend, router, _ = _make_engine(
        events, results, stop_on_error=True
    )
    record = engine.run_cycle()
    assert record.status in (RunStatus.PARTIAL_FAILURE, RunStatus.ERROR)
    assert cursor_backend.save.call_count == 1
    assert router.route.call_count == 2
    state_backend.write_run.assert_called_once()


def test_error_at_event2_stop_on_error_false_continues():
    events = [_make_event(f"evt_{i}") for i in range(3)]
    results = [
        _make_result(SyncAction.CREATED, "evt_0"),
        _make_result(SyncAction.ERROR, "evt_1"),
        _make_result(SyncAction.CREATED, "evt_2"),
    ]
    engine, _, cursor_backend, router, _ = _make_engine(
        events, results, stop_on_error=False
    )
    record = engine.run_cycle()
    assert record.status == RunStatus.PARTIAL_FAILURE
    assert router.route.call_count == 3
    assert cursor_backend.save.call_count == 2


def test_state_writer_called_exactly_once():
    events = [_make_event("evt_0")]
    results = [_make_result(SyncAction.CREATED, "evt_0")]
    engine, state_backend, _, _, _ = _make_engine(events, results)
    engine.run_cycle()
    state_backend.write_run.assert_called_once()


def test_trigger_source_propagates():
    engine, _, _, _, _ = _make_engine([], [])
    record = engine.run_cycle(trigger_source="dashboard")
    assert record.trigger_source == "dashboard"


# ── Watched-group filter tests ────────────────────────────────────────────────


def test_user_created_skipped_when_not_in_watched_group():
    """User not in any watched group should be skipped, not routed."""
    events = [_make_event("evt_0", "dsync.user.created")]
    engine, _, cursor_backend, router, workos_client = _make_engine(
        events,
        [],
        watched_groups={"ninjaone-users"},
        user_groups=["other-group"],
    )
    record = engine.run_cycle()
    router.route.assert_not_called()
    workos_client.get_user_group_names.assert_called_once_with("dir_user_001")
    cursor_backend.save.assert_called_once_with("evt_0")
    assert record.status == RunStatus.SUCCESS
    assert record.events_fetched == 1
    assert record.events_processed == 0


def test_user_created_routed_when_in_watched_group():
    """User in a watched group should be routed normally."""
    events = [_make_event("evt_0", "dsync.user.created")]
    results = [_make_result(SyncAction.CREATED, "evt_0")]
    engine, _, cursor_backend, router, _ = _make_engine(
        events,
        results,
        watched_groups={"ninjaone-users"},
        user_groups=["ninjaone-users"],
    )
    record = engine.run_cycle()
    router.route.assert_called_once()
    cursor_backend.save.assert_called_once_with("evt_0")
    assert record.status == RunStatus.SUCCESS


def test_user_updated_skipped_when_not_in_watched_group():
    """dsync.user.updated also filtered by group membership."""
    events = [_make_event("evt_0", "dsync.user.updated")]
    engine, _, _, router, _ = _make_engine(
        events,
        [],
        watched_groups={"ninjaone-users"},
        user_groups=[],
    )
    engine.run_cycle()
    router.route.assert_not_called()


def test_user_deleted_always_routed_regardless_of_group():
    """Delete events bypass group filtering — must deactivate if user exists."""
    event = _make_event("evt_0", "dsync.user.deleted")
    results = [_make_result(SyncAction.DEACTIVATED, "evt_0")]
    engine, _, cursor_backend, router, workos_client = _make_engine(
        [event],
        results,
        watched_groups={"ninjaone-users"},
        user_groups=[],
    )
    engine.run_cycle()
    router.route.assert_called_once()
    workos_client.get_user_group_names.assert_not_called()
    cursor_backend.save.assert_called_once_with("evt_0")


def test_group_cache_prevents_duplicate_workos_calls():
    """Two events for the same user should trigger only one WorkOS group lookup."""
    events = [
        _make_event("evt_0", "dsync.user.created"),
        _make_event("evt_1", "dsync.user.updated"),
    ]
    results = [
        _make_result(SyncAction.CREATED, "evt_0"),
        _make_result(SyncAction.UPDATED, "evt_1"),
    ]
    engine, _, _, _, workos_client = _make_engine(
        events,
        results,
        watched_groups={"ninjaone-users"},
        user_groups=["ninjaone-users"],
    )
    engine.run_cycle()
    workos_client.get_user_group_names.assert_called_once_with("dir_user_001")


def test_allow_all_when_no_watched_groups():
    """Empty watched_groups means all users pass — no WorkOS group lookup."""
    events = [_make_event("evt_0", "dsync.user.created")]
    results = [_make_result(SyncAction.CREATED, "evt_0")]
    engine, _, _, router, workos_client = _make_engine(
        events,
        results,
        watched_groups=set(),
    )
    engine.run_cycle()
    router.route.assert_called_once()
    workos_client.get_user_group_names.assert_not_called()


# ── Prefetch tests ────────────────────────────────────────────────────────────


def test_group_memberships_prefetched_before_processing():
    """When watched_groups is set, all WorkOS lookups happen before NinjaOne calls."""
    events = [
        _make_event("evt_0", "dsync.user.created"),
        _make_event("evt_1", "dsync.user.updated"),
    ]
    results = [
        _make_result(SyncAction.CREATED, "evt_0"),
        _make_result(SyncAction.UPDATED, "evt_1"),
    ]
    call_order: list[str] = []

    engine, _, _, router, workos_client = _make_engine(
        events,
        results,
        watched_groups={"ninjaone-users"},
        user_groups=["ninjaone-users"],
    )
    workos_client.get_user_group_names.side_effect = lambda uid: (
        call_order.append(f"workos:{uid}") or ["ninjaone-users"]
    )
    router.route.side_effect = lambda *a: (
        call_order.append("ninjaone_call") or results.pop(0)
    )

    engine.run_cycle()

    first_ninjaone = next(i for i, v in enumerate(call_order) if v == "ninjaone_call")
    last_workos = max(
        (i for i, v in enumerate(call_order) if v.startswith("workos:")), default=-1
    )
    assert last_workos < first_ninjaone


def test_no_prefetch_when_no_filters():
    """With no watched_groups and no admin_group, no WorkOS lookups at all."""
    events = [_make_event("evt_0", "dsync.user.created")]
    results = [_make_result(SyncAction.CREATED, "evt_0")]
    engine, _, _, _, workos_client = _make_engine(
        events,
        results,
        watched_groups=set(),
        admin_group="",
    )
    engine.run_cycle()
    workos_client.get_user_group_names.assert_not_called()


# ── Admin group bypass tests ──────────────────────────────────────────────────


def test_admin_group_member_skipped_on_user_created():
    """Users in admin group are skipped for dsync.user.created."""
    events = [_make_event("evt_0", "dsync.user.created")]
    engine, _, cursor_backend, router, _ = _make_engine(
        events,
        [],
        admin_group="ninjaone-admins",
        user_groups=["ninjaone-admins"],
    )
    record = engine.run_cycle()
    router.route.assert_not_called()
    cursor_backend.save.assert_called_once_with("evt_0")
    assert record.events_processed == 0


def test_admin_group_member_skipped_on_user_updated():
    """Users in admin group are skipped for dsync.user.updated."""
    events = [_make_event("evt_0", "dsync.user.updated")]
    engine, _, cursor_backend, router, _ = _make_engine(
        events,
        [],
        admin_group="ninjaone-admins",
        user_groups=["ninjaone-admins"],
    )
    engine.run_cycle()
    router.route.assert_not_called()
    cursor_backend.save.assert_called_once_with("evt_0")


def test_admin_group_member_deleted_still_processed():
    """dsync.user.deleted for admin group members is NOT skipped."""
    event = _make_event("evt_0", "dsync.user.deleted")
    results = [_make_result(SyncAction.DEACTIVATED, "evt_0")]
    engine, _, cursor_backend, router, workos_client = _make_engine(
        [event],
        results,
        admin_group="ninjaone-admins",
        user_groups=["ninjaone-admins"],
    )
    engine.run_cycle()
    router.route.assert_called_once()
    workos_client.get_user_group_names.assert_not_called()
    cursor_backend.save.assert_called_once_with("evt_0")


def test_non_admin_user_not_affected_by_admin_group_setting():
    """Users not in admin group process normally even when admin_group is configured."""
    events = [_make_event("evt_0", "dsync.user.created")]
    results = [_make_result(SyncAction.CREATED, "evt_0")]
    engine, _, _, router, _ = _make_engine(
        events,
        results,
        admin_group="ninjaone-admins",
        user_groups=["ninjaone-users"],
    )
    engine.run_cycle()
    router.route.assert_called_once()


def test_admin_check_takes_priority_over_watched_groups():
    """Admin group skip fires before watched_groups check."""
    events = [_make_event("evt_0", "dsync.user.created")]
    engine, _, cursor_backend, router, _ = _make_engine(
        events,
        [],
        watched_groups={"ninjaone-users"},
        admin_group="ninjaone-admins",
        user_groups=["ninjaone-admins"],
    )
    engine.run_cycle()
    router.route.assert_not_called()
    cursor_backend.save.assert_called_once_with("evt_0")


def test_admin_group_member_skipped_on_group_user_added():
    """Users in admin group are also skipped for dsync.group.user_added."""
    event = {
        "id": "evt_0",
        "event": "dsync.group.user_added",
        "data": {
            "id": "dir_user_001",
            "user": {
                "email": "alice@example.com",
                "first_name": "Alice",
                "last_name": "Smith",
                "state": "active",
                "custom_attributes": {},
            },
            "group": {"name": "ninjaone-users"},
        },
    }
    engine, _, cursor_backend, router, _ = _make_engine(
        [event],
        [],
        admin_group="ninjaone-admins",
        user_groups=["ninjaone-admins", "ninjaone-users"],
    )
    record = engine.run_cycle()
    router.route.assert_not_called()
    cursor_backend.save.assert_called_once_with("evt_0")
    assert record.events_processed == 0
