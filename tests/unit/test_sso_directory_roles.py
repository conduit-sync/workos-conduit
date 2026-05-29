from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.auth.directory_access import directory_user_role_slugs, find_directory_user_by_email
from src.auth.sso import SSOAccessDeniedError, WorkOSSSOService


def _directory_user(email: str, role_slugs: list[str]):
    user = MagicMock()
    user.email = email
    user.role = None
    user.roles = [MagicMock(slug=slug) for slug in role_slugs]
    return user


def _page(users, after=None):
    page = MagicMock()
    page.data = users
    page.after = after
    return page


def test_directory_user_role_slugs_collects_roles() -> None:
    user = _directory_user("ops@example.com", ["role-a", "role-b"])
    assert directory_user_role_slugs(user) == {"role-a", "role-b"}


def test_find_directory_user_by_email_paginates() -> None:
    client = MagicMock()
    first = _page([_directory_user("other@example.com", [])])
    first.after = "cursor_page_2"
    client.directory_sync.list_users.side_effect = [
        first,
        _page([_directory_user("ops@example.com", ["admin"])]),
    ]
    found = find_directory_user_by_email(
        client,
        directory_id="directory_test",
        email="ops@example.com",
    )
    assert found is not None
    assert found.email == "ops@example.com"
    assert client.directory_sync.list_users.call_count == 2


def test_validate_login_roles_allows_matching_slug(settings_override) -> None:
    settings = settings_override.model_copy(
        update={
            "workos_sso_client_id": "client_test",
            "workos_sso_role_slugs": "app-workos-conduit-admin-role",
        }
    )
    service = WorkOSSSOService(settings)
    service._validate_login_roles({"app-workos-conduit-admin-role"})


def test_load_directory_roles_denies_missing_user(settings_override) -> None:
    settings = settings_override.model_copy(
        update={
            "workos_sso_client_id": "client_test",
            "workos_sso_role_slugs": "app-workos-conduit-admin-role",
        }
    )
    service = WorkOSSSOService(settings)
    service._client = MagicMock()
    service._client.directory_sync.list_users.return_value = _page([])

    with pytest.raises(SSOAccessDeniedError) as exc_info:
        service._load_directory_roles("missing@example.com")
    assert exc_info.value.reason == "directory_user_not_found"


def test_validate_login_roles_denies_wrong_role(settings_override) -> None:
    settings = settings_override.model_copy(
        update={
            "workos_sso_client_id": "client_test",
            "workos_sso_role_slugs": "app-workos-conduit-admin-role",
        }
    )
    service = WorkOSSSOService(settings)

    with pytest.raises(SSOAccessDeniedError) as exc_info:
        service._validate_login_roles({"other-role"})
    assert exc_info.value.reason == "directory_role_not_authorized"


def test_load_directory_roles_returns_slugs(settings_override) -> None:
    settings = settings_override.model_copy(
        update={"workos_sso_client_id": "client_test"}
    )
    service = WorkOSSSOService(settings)
    service._client = MagicMock()
    service._client.directory_sync.list_users.return_value = _page(
        [_directory_user("ops@example.com", ["app-workos-conduit-user-role"])]
    )

    roles = service._load_directory_roles("ops@example.com")
    assert roles == {"app-workos-conduit-user-role"}
