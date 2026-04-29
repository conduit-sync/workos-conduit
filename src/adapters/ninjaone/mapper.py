# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from src.adapters.base import ProvisioningUser


def workos_to_ninjaone(user: ProvisioningUser) -> dict:
    """Maps ProvisioningUser → NinjaOne technician create/update payload."""
    return {
        "firstName": user.first_name,
        "lastName": user.last_name,
        "email": user.email,
        "userType": "TECHNICIAN",
        "mustChangePassword": False,
        "enabled": user.is_active,
    }


def workos_group_to_ninjaone_role(
    group_name: str, role_map: dict[str, str]
) -> str | None:
    """
    Looks up group_name in role_map.
    role_map loaded from NINJAONE_GROUP_ROLE_MAP env var (JSON string).
    Returns None if group_name not found — caller logs warning, does not fail.
    """
    return role_map.get(group_name)
