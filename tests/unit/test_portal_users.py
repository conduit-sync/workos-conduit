from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from datetime import datetime, timezone

from src.workos.portal_users import PortalUsersService, _format_created_at


def test_format_created_at_matches_workos_style() -> None:
    dt = datetime(2026, 5, 29, 7, 9, tzinfo=timezone.utc)
    assert _format_created_at(dt) == "May 29, 2026 7:09 AM"


def test_invite_user_sends_invitation_and_sets_metadata(settings_override):
    settings = settings_override.model_copy(
        update={
            "workos_customer_portal_api_key": "sk_portal",
            "workos_customer_portal_organization_id": "org_portal",
            "workos_customer_portal_invite_role_slug": "portal-member",
            "workos_customer_portal_user_client_id_metadata_key": "client_id",
        }
    )
    service = PortalUsersService(settings)
    service._client = MagicMock()

    existing = MagicMock()
    existing.id = "user_01"
    existing.email = "new@example.com"
    existing.first_name = "New"
    existing.last_name = "User"
    existing.metadata = {"other": "x"}
    service._client.user_management.list_users.return_value = MagicMock(data=[existing])

    updated = MagicMock()
    updated.id = "user_01"
    updated.email = "new@example.com"
    updated.first_name = "New"
    updated.last_name = "User"
    updated.metadata = {"other": "x", "client_id": "42"}
    service._client.user_management.update_user.return_value = updated

    row = service.invite_user(email="new@example.com", client_id="42")

    service._client.user_management.send_invitation.assert_called_once_with(
        email="new@example.com",
        organization_id="org_portal",
        role_slug="portal-member",
    )
    service._client.user_management.update_user.assert_called_once_with(
        "user_01",
        metadata={"other": "x", "client_id": "42"},
    )
    service._client.user_management.create_user.assert_not_called()
    assert row.client_id == "42"
    assert row.email == "new@example.com"


def test_invite_user_creates_user_when_not_found(settings_override):
    settings = settings_override.model_copy(
        update={
            "workos_customer_portal_organization_id": "org_portal",
            "workos_customer_portal_invite_role_slug": "portal-member",
        }
    )
    service = PortalUsersService(settings)
    service._client = MagicMock()
    service._client.user_management.list_users.return_value = MagicMock(data=[])

    created = MagicMock()
    created.id = "user_02"
    created.email = "new@example.com"
    created.first_name = ""
    created.last_name = ""
    created.metadata = {"client_id": "99"}
    service._client.user_management.create_user.return_value = created

    row = service.invite_user(email="new@example.com", client_id="99")

    service._client.user_management.create_user.assert_called_once_with(
        email="new@example.com",
        metadata={"client_id": "99"},
    )
    assert row.client_id == "99"


def test_invite_user_requires_org(settings_override):
    settings = settings_override.model_copy(
        update={"workos_customer_portal_organization_id": ""}
    )
    service = PortalUsersService(settings)
    with pytest.raises(ValueError, match="WORKOS_CUSTOMER_PORTAL_ORGANIZATION_ID"):
        service.invite_user(email="a@b.com", client_id="1")


def test_invite_user_requires_role_slug(settings_override):
    settings = settings_override.model_copy(
        update={
            "workos_customer_portal_organization_id": "org_portal",
            "workos_customer_portal_invite_role_slug": "",
            "workos_customer_portal_invite_role_slug": "",
        }
    )
    service = PortalUsersService(settings)
    with pytest.raises(ValueError, match="INVITE_ROLE_SLUG"):
        service.invite_user(email="a@b.com", client_id="1")


def test_list_users_reads_client_id_from_metadata(settings_override):
    settings = settings_override.model_copy(
        update={
            "workos_customer_portal_organization_id": "org_portal",
            "workos_customer_portal_user_client_id_metadata_key": "client_id",
        }
    )
    service = PortalUsersService(settings)
    service._client = MagicMock()

    user = MagicMock()
    user.id = "user_01"
    user.email = "ops@example.com"
    user.first_name = "Ops"
    user.last_name = "User"
    user.metadata = {"client_id": "1001"}
    user.created_at = datetime(2026, 5, 20, 18, 53, tzinfo=timezone.utc)

    users_page = MagicMock()
    users_page.auto_paging_iter.return_value = iter([user])
    service._client.user_management.list_users.return_value = users_page

    inv_page = MagicMock()
    inv_page.auto_paging_iter.return_value = iter([])
    service._client.user_management.list_invitations.return_value = inv_page

    rows = service.list_users()
    assert len(rows) == 1
    assert rows[0].client_id == "1001"
    assert rows[0].first_name == "Ops"
    assert rows[0].membership == "active"
    assert rows[0].created_at_label == "May 20, 2026 6:53 PM"


def test_list_users_includes_pending_invitations(settings_override):
    settings = settings_override.model_copy(
        update={
            "workos_customer_portal_organization_id": "org_portal",
            "workos_customer_portal_user_client_id_metadata_key": "client_id",
        }
    )
    service = PortalUsersService(settings)
    service._client = MagicMock()

    users_page = MagicMock()
    users_page.auto_paging_iter.return_value = iter([])
    service._client.user_management.list_users.return_value = users_page

    invitation = MagicMock()
    invitation.id = "inv_01"
    invitation.email = "pending@example.com"
    invitation.state = "pending"
    invitation.created_at = datetime(2026, 5, 29, 7, 9, tzinfo=timezone.utc)

    inv_page = MagicMock()
    inv_page.auto_paging_iter.return_value = iter([invitation])
    service._client.user_management.list_invitations.return_value = inv_page

    pending_user = MagicMock()
    pending_user.id = "user_02"
    pending_user.email = "pending@example.com"
    pending_user.first_name = ""
    pending_user.last_name = ""
    pending_user.metadata = {"client_id": "55"}
    pending_user.created_at = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)
    service._client.user_management.list_users.side_effect = [
        users_page,
        MagicMock(data=[pending_user]),
    ]

    rows = service.list_users()
    assert len(rows) == 1
    assert rows[0].email == "pending@example.com"
    assert rows[0].client_id == "55"
    assert rows[0].membership == "pending"
    assert rows[0].created_at_label == "May 29, 2026 7:09 AM"
