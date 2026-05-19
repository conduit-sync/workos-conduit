from __future__ import annotations

from unittest.mock import patch

from src.adapters.base import ProvisioningGroup, ProvisioningUser
from src.adapters.ninjaone.adapter import NinjaOneAdapter
from src.adapters.ninjaone.client import NinjaOneEmailAlreadyInUse
from src.adapters.ninjaone.group_role_map import OrgGroupMapping
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


def _make_mapping(
    group: str = "ninjaone-users",
    org_id: int = 1,
    role: str = "END_USER",
) -> OrgGroupMapping:
    return OrgGroupMapping(
        ninjaone_organization_name="Test Org",
        ninjaone_organization_id=org_id,
        google_workspace_group_name=group,
        ninjaone_role=role,
    )


def _make_adapter(settings_override, role_map: dict | None = None):
    if role_map is None:
        role_map = {"ninjaone-users": _make_mapping()}
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
    adapter._client.find_end_user_by_email.return_value = None
    adapter._client.create_end_user.return_value = {"id": 42}

    result = adapter.provision_user_created(_make_user())
    assert result.action == SyncAction.CREATED
    assert result.target_user_id == "42"
    adapter._client.create_end_user.assert_called_once()


def test_user_created_already_exists(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_end_user_by_email.return_value = {
        "id": 99,
        "email": "alice@example.com",
    }

    result = adapter.provision_user_created(_make_user())
    assert result.action == SyncAction.SKIPPED
    adapter._client.create_end_user.assert_not_called()


def test_user_created_passes_org_id(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_end_user_by_email.return_value = None
    adapter._client.create_end_user.return_value = {"id": 7}

    adapter.provision_user_created(_make_user(), org_id=42)
    payload = adapter._client.create_end_user.call_args[0][0]
    assert payload["organizationId"] == 42


def test_user_created_email_already_in_use_skips(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_end_user_by_email.return_value = None
    adapter._client.create_end_user.side_effect = NinjaOneEmailAlreadyInUse(
        409,
        '{"resultCode":"EMAIL_ALREADY_IN_USE"}',
    )

    result = adapter.provision_user_created(_make_user())
    assert result.action == SyncAction.SKIPPED


# ── provision_user_updated ────────────────────────────────────────────────────


def test_user_updated_with_diff(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_end_user_by_email.return_value = {
        "id": 10,
        "firstName": "OldFirst",
        "lastName": "Smith",
        "enabled": True,
    }
    adapter._client.update_end_user.return_value = {}

    result = adapter.provision_user_updated(_make_user(first_name="Alice"))
    assert result.action == SyncAction.UPDATED
    assert "firstName" in result.changed_fields


def test_user_updated_no_diff(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_end_user_by_email.return_value = {
        "id": 10,
        "firstName": "Alice",
        "lastName": "Smith",
        "enabled": True,
    }

    result = adapter.provision_user_updated(_make_user())
    assert result.action == SyncAction.NO_CHANGE
    adapter._client.update_end_user.assert_not_called()


def test_user_updated_not_found_creates(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_end_user_by_email.side_effect = [None, {"id": 20}]
    adapter._client.create_end_user.return_value = {"id": 20}

    result = adapter.provision_user_updated(_make_user())
    assert result.action in (SyncAction.CREATED, SyncAction.SKIPPED)


# ── provision_user_deactivated ────────────────────────────────────────────────


def test_user_deactivated(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_end_user_by_email.return_value = {"id": 5, "enabled": True}
    adapter._client.deactivate_end_user.return_value = None

    result = adapter.provision_user_deactivated(_make_user())
    assert result.action == SyncAction.DEACTIVATED
    adapter._client.deactivate_end_user.assert_called_once_with(5)


def test_user_deactivated_not_found(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_end_user_by_email.return_value = None

    result = adapter.provision_user_deactivated(_make_user())
    assert result.action == SyncAction.NOT_FOUND_SKIPPED


def test_user_deactivated_already_inactive(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.find_end_user_by_email.return_value = {"id": 5, "enabled": False}

    result = adapter.provision_user_deactivated(_make_user())
    assert result.action == SyncAction.ALREADY_INACTIVE
    adapter._client.deactivate_end_user.assert_not_called()


# ── provision_group_membership ────────────────────────────────────────────────


def test_group_membership_added_end_user_creates(settings_override):
    """user_added with END_USER role creates the user if they don't exist."""
    role_map = {"ninjaone-users": _make_mapping(group="ninjaone-users", org_id=111)}
    adapter = _make_adapter(settings_override, role_map=role_map)
    adapter._client.find_end_user_by_email.return_value = None
    adapter._client.create_end_user.return_value = {"id": 7}

    group = ProvisioningGroup(
        user=_make_user(), group_name="ninjaone-users", action="added"
    )
    result = adapter.provision_group_membership(group)
    assert result.action == SyncAction.CREATED
    adapter._client.create_end_user.assert_called_once()
    payload = adapter._client.create_end_user.call_args[0][0]
    assert payload["organizationId"] == 111


def test_group_membership_added_end_user_skips_when_org_matches(settings_override):
    """user_added when user already exists with correct org returns SKIPPED."""
    role_map = {"ninjaone-users": _make_mapping(group="ninjaone-users", org_id=111)}
    adapter = _make_adapter(settings_override, role_map=role_map)
    adapter._client.find_end_user_by_email.return_value = {
        "id": 7,
        "firstName": "Alice",
        "lastName": "Smith",
        "organizationId": 111,
    }

    group = ProvisioningGroup(
        user=_make_user(), group_name="ninjaone-users", action="added"
    )
    result = adapter.provision_group_membership(group)
    assert result.action == SyncAction.SKIPPED
    adapter._client.create_end_user.assert_not_called()
    adapter._client.update_end_user.assert_not_called()


def test_group_membership_added_updates_org_when_changed(settings_override):
    """user_added when user exists with a different org → UPDATED with organizationId patched."""
    role_map = {"ninjaone-users": _make_mapping(group="ninjaone-users", org_id=999)}
    adapter = _make_adapter(settings_override, role_map=role_map)
    adapter._client.find_end_user_by_email.return_value = {
        "id": 8,
        "firstName": "Alice",
        "lastName": "Smith",
        "organizationId": 111,
    }
    adapter._client.update_end_user.return_value = {}

    group = ProvisioningGroup(
        user=_make_user(), group_name="ninjaone-users", action="added"
    )
    result = adapter.provision_group_membership(group)
    assert result.action == SyncAction.UPDATED
    assert "organizationId" in result.changed_fields
    adapter._client.update_end_user.assert_called_once_with(8, {"organizationId": 999})


def test_group_membership_removed_deactivates(settings_override):
    """user_removed with END_USER role deactivates the user."""
    role_map = {"ninjaone-users": _make_mapping(group="ninjaone-users")}
    adapter = _make_adapter(settings_override, role_map=role_map)
    adapter._client.find_end_user_by_email.return_value = {"id": 5, "enabled": True}

    group = ProvisioningGroup(
        user=_make_user(), group_name="ninjaone-users", action="removed"
    )
    result = adapter.provision_group_membership(group)
    assert result.action == SyncAction.DEACTIVATED
    adapter._client.deactivate_end_user.assert_called_once_with(5)


def test_group_membership_no_role_mapping_skipped(settings_override):
    """Group with no role mapping is skipped."""
    adapter = _make_adapter(settings_override, role_map={})

    group = ProvisioningGroup(
        user=_make_user(), group_name="Unknown Group", action="added"
    )
    result = adapter.provision_group_membership(group)
    assert result.action == SyncAction.SKIPPED
    adapter._client.create_end_user.assert_not_called()


def test_group_membership_unsupported_role_skipped(settings_override):
    """Group mapped to a non-END_USER role is skipped with a warning."""
    role_map = {"it-admins": _make_mapping(group="it-admins", role="administrator")}
    adapter = _make_adapter(settings_override, role_map=role_map)

    group = ProvisioningGroup(user=_make_user(), group_name="it-admins", action="added")
    result = adapter.provision_group_membership(group)
    assert result.action == SyncAction.SKIPPED
    adapter._client.create_end_user.assert_not_called()


# ── health_check ──────────────────────────────────────────────────────────────


def test_health_check_delegates_to_client(settings_override):
    adapter = _make_adapter(settings_override)
    adapter._client.health_check.return_value = True
    assert adapter.health_check() is True
