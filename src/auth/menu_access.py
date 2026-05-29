# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from src.config import Settings

NAV_SYNC = "sync"
NAV_PORTAL = "portal"


def parse_role_slugs(raw: str) -> set[str]:
    return {r.strip() for r in raw.split(",") if r.strip()}


def sync_board_roles(settings: Settings) -> set[str]:
    return parse_role_slugs(settings.workos_dashboard_sync_board_role_slugs)


def portal_roles(settings: Settings) -> set[str]:
    return parse_role_slugs(settings.workos_dashboard_portal_role_slugs)


def login_allowed_roles(settings: Settings) -> set[str]:
    """Roles that may sign in to the dashboard at all."""
    if settings.workos_sso_role_slugs.strip():
        return parse_role_slugs(settings.workos_sso_role_slugs)
    return sync_board_roles(settings) | portal_roles(settings)


def directory_roles_from_user(user: dict | None) -> set[str]:
    if not user:
        return set()
    return set(user.get("directory_roles") or [])


def can_access_sync(roles: set[str], settings: Settings) -> bool:
    if not settings.sso_enabled:
        return True
    required = sync_board_roles(settings)
    if not required:
        return True
    return bool(roles.intersection(required))


def can_access_portal(roles: set[str], settings: Settings) -> bool:
    if not settings.sso_enabled:
        return True
    required = portal_roles(settings)
    if not required:
        return True
    return bool(roles.intersection(required))


def can_access_nav(roles: set[str], settings: Settings, nav: str) -> bool:
    if nav == NAV_SYNC:
        return can_access_sync(roles, settings)
    if nav == NAV_PORTAL:
        return can_access_portal(roles, settings)
    return False


def nav_access_context(settings: Settings, user: dict | None) -> dict[str, bool]:
    roles = directory_roles_from_user(user)
    return {
        "can_access_sync": can_access_sync(roles, settings),
        "can_access_portal": can_access_portal(roles, settings),
    }


def post_login_redirect_url(settings: Settings, user: dict) -> str:
    ctx = nav_access_context(settings, user)
    if ctx["can_access_sync"]:
        return "/"
    if ctx["can_access_portal"]:
        return "/portal/users"
    return "/login?error=directory_role_not_authorized"
