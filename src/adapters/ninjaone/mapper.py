# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from src.adapters.base import ProvisioningUser


def workos_to_ninjaone(user: ProvisioningUser, org_id: int | None = None) -> dict:
    """Maps ProvisioningUser → NinjaOne end-user create payload."""
    payload: dict = {
        "firstName": user.first_name,
        "lastName": user.last_name,
        "email": user.email,
        "fullPortalAccess": False,
    }
    if org_id is not None:
        payload["organizationId"] = org_id
    return payload


def workos_to_ninjaone_update(user: ProvisioningUser) -> dict:
    """Maps ProvisioningUser → NinjaOne end-user update payload."""
    return {
        "firstName": user.first_name,
        "lastName": user.last_name,
    }


def workos_group_to_ninjaone_role(
    group_name: str, role_map: dict[str, str]
) -> str | None:
    """Looks up group_name in role_map. Returns None if not found."""
    return role_map.get(group_name)
