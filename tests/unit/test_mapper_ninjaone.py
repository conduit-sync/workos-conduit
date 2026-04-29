from __future__ import annotations

from src.adapters.base import ProvisioningUser
from src.adapters.ninjaone.mapper import (
    workos_group_to_ninjaone_role,
    workos_to_ninjaone,
)


def _make_user(is_active: bool = True) -> ProvisioningUser:
    return ProvisioningUser(
        email="alice@example.com",
        first_name="Alice",
        last_name="Smith",
        is_active=is_active,
        department="Engineering",
        job_title="Engineer",
        external_id="dir_user_001",
    )


def test_active_user_enabled_true():
    payload = workos_to_ninjaone(_make_user(is_active=True), org_id="org1")
    assert payload["enabled"] is True


def test_inactive_user_enabled_false():
    payload = workos_to_ninjaone(_make_user(is_active=False), org_id="org1")
    assert payload["enabled"] is False


def test_required_fields_present():
    payload = workos_to_ninjaone(_make_user(), org_id="org1")
    assert "firstName" in payload
    assert "lastName" in payload
    assert "email" in payload
    assert payload["userType"] == "TECHNICIAN"


def test_no_custom_attributes_does_not_raise():
    user = ProvisioningUser(
        email="bob@example.com",
        first_name="Bob",
        last_name="Jones",
        is_active=True,
        external_id="dir_user_002",
    )
    payload = workos_to_ninjaone(user, org_id="org1")
    assert payload["email"] == "bob@example.com"


def test_group_role_known():
    role_map = {"IT Admins": "administrator", "Support": "technician"}
    assert workos_group_to_ninjaone_role("IT Admins", role_map) == "administrator"
    assert workos_group_to_ninjaone_role("Support", role_map) == "technician"


def test_group_role_unknown_returns_none():
    role_map = {"IT Admins": "administrator"}
    assert workos_group_to_ninjaone_role("Unknown Group", role_map) is None


def test_group_role_empty_map_returns_none():
    assert workos_group_to_ninjaone_role("IT Admins", {}) is None
