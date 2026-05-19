from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.adapters.base import BaseTargetAdapter
from src.core.event_router import EventRouter
from src.core.models import HandlerResult, SyncAction
from src.handlers.group_membership import GroupMembershipHandler
from src.handlers.user_created import UserCreatedHandler
from src.handlers.user_deleted import UserDeletedHandler
from src.handlers.user_updated import UserUpdatedHandler


def _make_event(event_type: str, event_id: str = "evt_001") -> dict:
    data = {
        "id": "directory_user_001",
        "email": "alice@example.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "state": "active",
        "custom_attributes": {},
    }
    if "group" in event_type:
        return {
            "id": event_id,
            "event": event_type,
            "data": {
                "user": data,
                "group": {"id": "grp_001", "name": "IT Admins"},
            },
        }
    return {"id": event_id, "event": event_type, "data": data}


def _make_router() -> EventRouter:
    return EventRouter(
        [
            UserCreatedHandler(),
            UserUpdatedHandler(),
            UserDeletedHandler(),
            GroupMembershipHandler(),
        ]
    )


def _make_mock_adapter() -> MagicMock:
    adapter = MagicMock(spec=BaseTargetAdapter)
    adapter.adapter_key = "ninjaone"
    result = HandlerResult(
        event_id="evt_001",
        event_type="dsync.user.created",
        action=SyncAction.CREATED,
        target_adapter="ninjaone",
        email="alice@example.com",
    )
    adapter.provision_user_created.return_value = result
    adapter.provision_user_updated.return_value = result
    adapter.provision_user_deactivated.return_value = result
    adapter.provision_group_membership.return_value = result
    return adapter


@pytest.mark.parametrize(
    "event_type,method",
    [
        ("dsync.user.created", "provision_user_created"),
        ("dsync.user.updated", "provision_user_updated"),
        ("dsync.user.deleted", "provision_user_deactivated"),
        ("dsync.group.user_added", "provision_group_membership"),
        ("dsync.group.user_removed", "provision_group_membership"),
    ],
)
def test_routes_to_correct_handler(event_type: str, method: str):
    adapter = _make_mock_adapter()
    router = _make_router()
    result = router.route(_make_event(event_type), adapter)
    assert result.action != SyncAction.ERROR
    getattr(adapter, method).assert_called_once()


def test_unknown_event_type_returns_skipped():
    router = _make_router()
    adapter = _make_mock_adapter()
    result = router.route(
        {"id": "evt_x", "event": "unknown.event", "data": {}}, adapter
    )
    assert result.action == SyncAction.SKIPPED


def test_handler_exception_returns_error_does_not_propagate():
    adapter = _make_mock_adapter()
    adapter.provision_user_created.side_effect = RuntimeError("boom")
    router = _make_router()
    result = router.route(_make_event("dsync.user.created"), adapter)
    assert result.action == SyncAction.ERROR
    assert result.email == "alice@example.com"
    assert "boom" in result.error_message


def test_group_handler_exception_includes_nested_user_email():
    adapter = _make_mock_adapter()
    adapter.provision_group_membership.side_effect = RuntimeError("group boom")
    router = _make_router()
    result = router.route(_make_event("dsync.group.user_added"), adapter)
    assert result.action == SyncAction.ERROR
    assert result.email == "alice@example.com"
    assert "group boom" in result.error_message
