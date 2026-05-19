# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from src.handlers.base import BaseEventHandler

_HANDLERS: list[type[BaseEventHandler]] = []


def register_handler(cls: type[BaseEventHandler]) -> type[BaseEventHandler]:
    """Register an event handler class. Used as a decorator in this module."""
    _HANDLERS.append(cls)
    return cls


def get_handlers() -> list[BaseEventHandler]:
    """Returns one fresh instance of each registered handler."""
    return [cls() for cls in _HANDLERS]


# Registration — import handlers here to avoid circular imports in the handler modules
from src.handlers.group_membership import GroupMembershipHandler  # noqa: E402
from src.handlers.user_created import UserCreatedHandler  # noqa: E402
from src.handlers.user_deleted import UserDeletedHandler  # noqa: E402
from src.handlers.user_updated import UserUpdatedHandler  # noqa: E402

register_handler(UserCreatedHandler)
register_handler(UserUpdatedHandler)
register_handler(UserDeletedHandler)
register_handler(GroupMembershipHandler)
