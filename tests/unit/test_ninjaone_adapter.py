from __future__ import annotations

from unittest.mock import patch

from src.adapters.base import ProvisioningGroup, ProvisioningUser
from src.adapters.ninjaone.adapter import NinjaOneAdapter
from src.core.models import SyncAction


def _make_user(**kwargs) -> ProvisioningUser:
    defaults = {
        "email": "alice@example.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "is_active": True,
        "external_id": "dir_usr_001",
    }
    return ProvisioningUser(**{**defaults, **kwargs})


def _make_adapter(settings_override, role_map: dict | None = None):
    if role_map is None:
        role_map = {"IT Admins": "administrator"}
    with (
        patch("src.adapters.ninjaone.adapter.NinjaOneAPIClient") as MockClient,
        patch(
            "src.adapters.ninjaone.adapter.load_group_role_map", return_value=role_map
        ),
    ):
        adapter = NinjaOneAdapter(settings_override)
        adapter._client = MockClient.return_value
    return adapter


# ── provision_user_created ────────────────────────────────────────────────────


def test_user_created_new_user(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_technician_by_email.return_value = None
    adapter._client.create_technician.return_value = {"id": 42}

    result = adapter.provision_user_created(_make_user())
    assert result.action == SyncAction.CREATED
    assert result.target_user_id == "42"
    adapter._client.create_technician.assert_called_once()


def test_user_created_already_exists(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_technician_by_email.return_value = {
        "id": 99,
        "email": "alice@example.com",
    }

    result = adapter.provision_user_created(_make_user())
    assert result.action == SyncAction.SKIPPED
    adapter._client.create_technician.assert_not_called()


# ── provision_user_updated ────────────────────────────────────────────────────


def test_user_updated_with_diff(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_technician_by_email.return_value = {
        "id": 10,
        "firstName": "OldFirst",
        "lastName": "Smith",
        "enabled": True,
    }
    adapter._client.update_technician.return_value = {}

    result = adapter.provision_user_updated(_make_user(first_name="Alice"))
    assert result.action == SyncAction.UPDATED
    assert "firstName" in result.changed_fields


def test_user_updated_no_diff(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_technician_by_email.return_value = {
        "id": 10,
        "firstName": "Alice",
        "lastName": "Smith",
        "enabled": True,
    }

    result = adapter.provision_user_updated(_make_user())
    assert result.action == SyncAction.NO_CHANGE
    adapter._client.update_technician.assert_not_called()


def test_user_updated_not_found_creates(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_technician_by_email.side_effect = [None, {"id": 20}]
    adapter._client.create_technician.return_value = {"id": 20}

    result = adapter.provision_user_updated(_make_user())
    assert result.action in (SyncAction.CREATED, SyncAction.SKIPPED)


# ── provision_user_deactivated ────────────────────────────────────────────────


def test_user_deactivated(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_technician_by_email.return_value = {"id": 5, "enabled": True}
    adapter._client.deactivate_technician.return_value = None

    result = adapter.provision_user_deactivated(_make_user())
    assert result.action == SyncAction.DEACTIVATED
    adapter._client.deactivate_technician.assert_called_once_with(5)


def test_user_deactivated_not_found(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_technician_by_email.return_value = None

    result = adapter.provision_user_deactivated(_make_user())
    assert result.action == SyncAction.NOT_FOUND_SKIPPED


def test_user_deactivated_already_inactive(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_technician_by_email.return_value = {"id": 5, "enabled": False}

    result = adapter.provision_user_deactivated(_make_user())
    assert result.action == SyncAction.ALREADY_INACTIVE
    adapter._client.deactivate_technician.assert_not_called()


# ── provision_group_membership ────────────────────────────────────────────────


def test_group_membership_role_assigned(settings_override):
    adapter = _make_adapter(settings_override, role_map={"IT Admins": "administrator"})
    adapter._client.find_technician_by_email.return_value = {"id": 7}
    adapter._client.update_technician.return_value = {}

    group = ProvisioningGroup(user=_make_user(), group_name="IT Admins", action="added")
    result = adapter.provision_group_membership(group)
    assert result.action == SyncAction.ROLE_ASSIGNED
    assert result.role == "administrator"


def test_group_membership_no_role_mapping(settings_override):
    adapter = _make_adapter(settings_override, role_map={})

    group = ProvisioningGroup(
        user=_make_user(), group_name="Unknown Group", action="added"
    )
    result = adapter.provision_group_membership(group)
    assert result.action == SyncAction.SKIPPED


def test_group_membership_user_not_found(settings_override):
    adapter = _make_adapter(settings_override, role_map={"IT Admins": "administrator"})
    adapter._client.find_technician_by_email.return_value = None

    group = ProvisioningGroup(user=_make_user(), group_name="IT Admins", action="added")
    result = adapter.provision_group_membership(group)
    assert result.action == SyncAction.NOT_FOUND_SKIPPED


# ── health_check ──────────────────────────────────────────────────────────────


def test_health_check_delegates_to_client(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.health_check.return_value = True
    assert adapter.health_check() is True
