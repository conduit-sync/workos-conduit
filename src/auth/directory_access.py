# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workos import WorkOSClient


def directory_user_role_slugs(directory_user) -> set[str]:
    """Collect role slugs from a Directory Sync user record."""
    slugs: set[str] = set()
    role = getattr(directory_user, "role", None)
    if role is not None:
        slug = getattr(role, "slug", None)
        if slug:
            slugs.add(slug)
    for entry in getattr(directory_user, "roles", None) or []:
        slug = getattr(entry, "slug", None)
        if slug:
            slugs.add(slug)
    return slugs


def find_directory_user_by_email(
    client: WorkOSClient,
    *,
    directory_id: str,
    email: str,
    page_size: int = 100,
):
    """Find a directory user by email, paginating through the directory."""
    target = email.strip().lower()
    if not target:
        return None

    after: str | None = None
    while True:
        page = client.directory_sync.list_users(
            directory=directory_id,
            limit=page_size,
            after=after,
            order="desc",
        )
        users = page.data
        for user in users:
            user_email = getattr(user, "email", None)
            if user_email and user_email.strip().lower() == target:
                return user

        if not users:
            break
        after = page.after
        if not after:
            break

    return None
