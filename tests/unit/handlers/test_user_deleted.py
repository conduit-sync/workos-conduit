from __future__ import annotations

from unittest.mock import MagicMock

from src.adapters.base import BaseTargetAdapter
from src.core.models import HandlerResult, SyncAction
from src.handlers.user_deleted import UserDeletedHandler


def _make_adapter(action: SyncAction) -> MagicMock:
    adapter = MagicMock(spec=BaseTargetAdapter)
    adapter.adapter_key = "ninjaone"
    adapter.provision_user_deactivated.return_value = HandlerResult(
        event_id="",
        event_type="dsync.user.deleted",
        action=action,
        target_adapter="ninjaone",
        email="alice@example.com",
    )
    return adapter


def _make_event() -> dict:
    return {
        "id": "evt_003",
        "event": "dsync.user.deleted",
        "data": {
            "id": "dir_user_001",
            "email": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Smith",
            "state": "inactive",
            "custom_attributes": {},
        },
    }


def test_active_user_deactivated():
    adapter = _make_adapter(SyncAction.DEACTIVATED)
    result = UserDeletedHandler().handle(_make_event(), adapter)
    assert result.action == SyncAction.DEACTIVATED


def test_already_inactive_user():
    adapter = _make_adapter(SyncAction.ALREADY_INACTIVE)
    result = UserDeletedHandler().handle(_make_event(), adapter)
    assert result.action == SyncAction.ALREADY_INACTIVE


def test_user_not_found_in_target():
    adapter = _make_adapter(SyncAction.NOT_FOUND_SKIPPED)
    result = UserDeletedHandler().handle(_make_event(), adapter)
    assert result.action == SyncAction.NOT_FOUND_SKIPPED
