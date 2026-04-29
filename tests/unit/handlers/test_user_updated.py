from __future__ import annotations

from unittest.mock import MagicMock

from src.adapters.base import BaseTargetAdapter
from src.core.models import HandlerResult, SyncAction
from src.handlers.user_updated import UserUpdatedHandler


def _make_adapter(action: SyncAction, changed_fields=None) -> MagicMock:
    adapter = MagicMock(spec=BaseTargetAdapter)
    adapter.adapter_key = "ninjaone"
    adapter.provision_user_updated.return_value = HandlerResult(
        event_id="",
        event_type="dsync.user.updated",
        action=action,
        target_adapter="ninjaone",
        email="alice@example.com",
        changed_fields=changed_fields,
    )
    return adapter


def _make_event() -> dict:
    return {
        "id": "evt_002",
        "event": "dsync.user.updated",
        "data": {
            "id": "dir_user_001",
            "email": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Smith",
            "state": "active",
            "custom_attributes": {"job_title": "Senior Engineer"},
        },
    }


def test_user_updated_with_changes():
    adapter = _make_adapter(SyncAction.UPDATED, changed_fields=["firstName"])
    handler = UserUpdatedHandler()
    result = handler.handle(_make_event(), adapter)
    assert result.action == SyncAction.UPDATED
    assert result.changed_fields


def test_user_no_change():
    adapter = _make_adapter(SyncAction.NO_CHANGE)
    handler = UserUpdatedHandler()
    result = handler.handle(_make_event(), adapter)
    assert result.action == SyncAction.NO_CHANGE


def test_user_not_found_falls_through_to_created():
    adapter = _make_adapter(SyncAction.CREATED)
    handler = UserUpdatedHandler()
    result = handler.handle(_make_event(), adapter)
    assert result.action == SyncAction.CREATED
