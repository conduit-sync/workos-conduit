# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import structlog

from src.backends.base import CursorBackend

log = structlog.get_logger()


class MemoryCursorBackend(CursorBackend):
    """In-process cursor store for local development. State is lost on restart."""

    def __init__(self) -> None:
        self._cursor: str | None = None

    def get(self) -> str | None:
        return self._cursor

    def save(self, event_id: str) -> None:
        self._cursor = event_id
        log.debug("cursor_saved", event_id=event_id, cursor_backend="local")

    def health_check(self) -> bool:
        return True
