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


def test_required_fields_present():
    payload = workos_to_ninjaone(_make_user())
    assert payload["firstName"] == "Alice"
    assert payload["lastName"] == "Smith"
    assert payload["email"] == "alice@example.com"
    assert payload["fullPortalAccess"] is False


def test_org_id_included_when_provided():
    payload = workos_to_ninjaone(_make_user(), org_id=42)
    assert payload["organizationId"] == 42


def test_org_id_omitted_when_none():
    payload = workos_to_ninjaone(_make_user(), org_id=None)
    assert "organizationId" not in payload


def test_no_custom_attributes_does_not_raise():
    user = ProvisioningUser(
        email="bob@example.com",
        first_name="Bob",
        last_name="Jones",
        is_active=True,
        external_id="dir_user_002",
    )
    payload = workos_to_ninjaone(user)
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
