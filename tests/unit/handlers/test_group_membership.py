from __future__ import annotations

from unittest.mock import MagicMock

from src.adapters.base import BaseTargetAdapter
from src.core.models import HandlerResult, SyncAction
from src.handlers.group_membership import GroupMembershipHandler


def _make_adapter(action: SyncAction) -> MagicMock:
    adapter = MagicMock(spec=BaseTargetAdapter)
    adapter.adapter_key = "ninjaone"
    adapter.provision_group_membership.return_value = HandlerResult(
        event_id="",
        event_type="dsync.group.user_added",
        action=action,
        target_adapter="ninjaone",
        email="alice@example.com",
        role="administrator",
    )
    return adapter


def _make_event(event_type: str = "dsync.group.user_added") -> dict:
    return {
        "id": "evt_grp_001",
        "event": event_type,
        "data": {
            "user": {
                "id": "dir_user_001",
                "email": "alice@example.com",
                "first_name": "Alice",
                "last_name": "Smith",
                "state": "active",
                "custom_attributes": {},
            },
            "group": {"id": "grp_001", "name": "IT Admins"},
        },
    }


def test_group_with_role_mapping_added():
    adapter = _make_adapter(SyncAction.ROLE_ASSIGNED)
    result = GroupMembershipHandler().handle(
        _make_event("dsync.group.user_added"), adapter
    )
    assert result.action == SyncAction.ROLE_ASSIGNED


def test_group_with_no_mapping_skipped():
    adapter = _make_adapter(SyncAction.SKIPPED)
    result = GroupMembershipHandler().handle(
        _make_event("dsync.group.user_added"), adapter
    )
    assert result.action == SyncAction.SKIPPED


def test_group_removed_calls_adapter():
    adapter = _make_adapter(SyncAction.ROLE_ASSIGNED)
    GroupMembershipHandler().handle(_make_event("dsync.group.user_removed"), adapter)
    adapter.provision_group_membership.assert_called_once()
    call_args = adapter.provision_group_membership.call_args[0][0]
    assert call_args.action == "removed"


def test_handler_always_delegates_to_adapter():
    """Group filtering is the adapter's responsibility — handler never skips by group name."""
    adapter = _make_adapter(SyncAction.SKIPPED)
    GroupMembershipHandler().handle(_make_event("dsync.group.user_added"), adapter)
    adapter.provision_group_membership.assert_called_once()
