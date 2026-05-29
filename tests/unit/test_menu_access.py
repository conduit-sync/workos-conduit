from __future__ import annotations

from src.auth.menu_access import (
    NAV_PORTAL,
    NAV_SYNC,
    can_access_nav,
    can_access_portal,
    can_access_sync,
    login_allowed_roles,
    nav_access_context,
    post_login_redirect_url,
)


def _user(*roles: str) -> dict:
    return {"directory_roles": list(roles)}


def test_login_allowed_roles_defaults_to_nav_union(settings_override) -> None:
    settings = settings_override.model_copy(
        update={"workos_sso_internal_org_client_id": "client_test"}
    )
    assert login_allowed_roles(settings) == {
        "app-workos-conduit-admin-role",
        "app-workos-conduit-user-role",
    }


def test_login_allowed_roles_is_union_of_menu_roles(settings_override) -> None:
    settings = settings_override.model_copy(
        update={
            "workos_sso_internal_org_client_id": "client_test",
            "workos_dashboard_sync_board_role_slugs": "admin",
            "workos_dashboard_portal_role_slugs": "user,viewer",
        }
    )
    assert login_allowed_roles(settings) == {"admin", "user", "viewer"}


def test_admin_can_access_sync_and_portal(settings_override) -> None:
    settings = settings_override.model_copy(
        update={
            "workos_sso_internal_org_client_id": "client_test",
            "workos_dashboard_sync_board_role_slugs": "app-workos-conduit-admin-role",
            "workos_dashboard_portal_role_slugs": (
                "app-workos-conduit-admin-role,app-workos-conduit-user-role"
            ),
        }
    )
    user = _user("app-workos-conduit-admin-role")
    ctx = nav_access_context(settings, user)
    assert ctx["can_access_sync"] is True
    assert ctx["can_access_portal"] is True
    assert post_login_redirect_url(settings, user) == "/"


def test_user_role_portal_only(settings_override) -> None:
    settings = settings_override.model_copy(update={"workos_sso_internal_org_client_id": "client_test"})
    user = _user("app-workos-conduit-user-role")
    ctx = nav_access_context(settings, user)
    assert ctx["can_access_sync"] is False
    assert ctx["can_access_portal"] is True
    assert post_login_redirect_url(settings, user) == "/portal/users"
    assert can_access_nav({"app-workos-conduit-user-role"}, settings, NAV_SYNC) is False
    assert can_access_nav({"app-workos-conduit-user-role"}, settings, NAV_PORTAL) is True


def test_unknown_role_denied(settings_override) -> None:
    settings = settings_override.model_copy(update={"workos_sso_internal_org_client_id": "client_test"})
    roles = {"other-role"}
    assert can_access_sync(roles, settings) is False
    assert can_access_portal(roles, settings) is False


def test_sso_disabled_allows_all_sections(settings_override) -> None:
    settings = settings_override.model_copy(update={"workos_sso_internal_org_client_id": ""})
    assert can_access_sync(set(), settings) is True
    assert can_access_portal(set(), settings) is True
