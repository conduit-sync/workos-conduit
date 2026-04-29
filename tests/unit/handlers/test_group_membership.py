from __future__ import annotations

from unittest.mock import MagicMock

from src.adapters.base import BaseTargetAdapter
from src.config import get_settings
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
    # group action in ProvisioningGroup should be "removed"
    call_args = adapter.provision_group_membership.call_args[0][0]
    assert call_args.action == "removed"


# ---------------------------------------------------------------------------
# Group allow-list filtering
# ---------------------------------------------------------------------------


def test_group_not_in_allowed_list_is_skipped(monkeypatch):
    monkeypatch.setenv("SYNC_ALLOWED_GROUPS", '["Other Group"]')
    get_settings.cache_clear()
    adapter = _make_adapter(SyncAction.ROLE_ASSIGNED)
    result = GroupMembershipHandler().handle(
        _make_event("dsync.group.user_added"), adapter
    )
    assert result.action == SyncAction.SKIPPED
    adapter.provision_group_membership.assert_not_called()


def test_group_in_allowed_list_passes_through(monkeypatch):
    monkeypatch.setenv("SYNC_ALLOWED_GROUPS", '["IT Admins"]')
    get_settings.cache_clear()
    adapter = _make_adapter(SyncAction.ROLE_ASSIGNED)
    result = GroupMembershipHandler().handle(
        _make_event("dsync.group.user_added"), adapter
    )
    assert result.action == SyncAction.ROLE_ASSIGNED
    adapter.provision_group_membership.assert_called_once()


def test_empty_allowed_list_passes_all_groups(monkeypatch):
    monkeypatch.setenv("SYNC_ALLOWED_GROUPS", "[]")
    get_settings.cache_clear()
    adapter = _make_adapter(SyncAction.ROLE_ASSIGNED)
    result = GroupMembershipHandler().handle(
        _make_event("dsync.group.user_added"), adapter
    )
    assert result.action == SyncAction.ROLE_ASSIGNED
    adapter.provision_group_membership.assert_called_once()
