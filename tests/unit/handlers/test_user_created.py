from __future__ import annotations

from unittest.mock import MagicMock

from src.adapters.base import BaseTargetAdapter
from src.core.models import HandlerResult, SyncAction
from src.handlers.user_created import UserCreatedHandler


def _make_adapter(action: SyncAction) -> MagicMock:
    adapter = MagicMock(spec=BaseTargetAdapter)
    adapter.adapter_key = "ninjaone"
    adapter.provision_user_created.return_value = HandlerResult(
        event_id="",
        event_type="dsync.user.created",
        action=action,
        target_adapter="ninjaone",
        email="alice@example.com",
        target_user_id="123",
    )
    return adapter


def _make_event() -> dict:
    return {
        "id": "evt_001",
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


def test_user_does_not_exist_returns_created():
    adapter = _make_adapter(SyncAction.CREATED)
    handler = UserCreatedHandler()
    result = handler.handle(_make_event(), adapter)
    assert result.action == SyncAction.CREATED
    adapter.provision_user_created.assert_called_once()


def test_user_already_exists_returns_skipped():
    adapter = _make_adapter(SyncAction.SKIPPED)
    handler = UserCreatedHandler()
    result = handler.handle(_make_event(), adapter)
    assert result.action == SyncAction.SKIPPED
    # ensure no duplicate creation attempt
    adapter.provision_user_created.assert_called_once()


def test_event_id_set_on_result():
    adapter = _make_adapter(SyncAction.CREATED)
    handler = UserCreatedHandler()
    result = handler.handle(_make_event(), adapter)
    assert result.event_id == "evt_001"
