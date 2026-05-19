# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from src.backends.base import CursorBackend

if TYPE_CHECKING:
    from src.config import Settings

log = structlog.get_logger()


class FileCursorBackend(CursorBackend):
    """File-backed cursor store for local development. Survives restarts."""

    def __init__(self, settings: Settings) -> None:
        self._path = Path(settings.local_state_dir) / "cursor.txt"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> str | None:
        if not self._path.exists():
            return None
        value = self._path.read_text().strip()
        return value or None

    def save(self, event_id: str) -> None:
        self._path.write_text(event_id)
        log.debug("cursor_saved", event_id=event_id, cursor_backend="local")

    def health_check(self) -> bool:
        return self._path.parent.exists()
