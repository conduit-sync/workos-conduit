# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.models import RunRecord


class CursorBackend(ABC):
    """
    Persists the last-seen WorkOS event ID between sync cycles.
    Implementations: AWS SSM today; Azure AppConfig / GCS / local file later.
    """

    @abstractmethod
    def get(self) -> str | None:
        """Return saved event ID or None if unset (first run). Never raise on missing."""

    @abstractmethod
    def save(self, event_id: str) -> None:
        """Overwrite saved event ID. Called once per successfully processed event."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the cursor store is reachable."""


class StateBackend(ABC):
    """
    Persists immutable RunRecord JSON documents.
    Implementations: AWS S3 today; Azure Blob / GCS / local filesystem later.
    """

    @abstractmethod
    def write_run(self, record: RunRecord) -> str:
        """Serialise and persist a RunRecord. Return backend-specific key/URI. APPEND-ONLY."""

    @abstractmethod
    def get_run(self, run_id: str) -> RunRecord | None:
        """Return single RunRecord by ID. None if not found."""

    @abstractmethod
    def list_recent_runs(self, limit: int) -> list[RunRecord]:
        """Return up to `limit` most recent runs, sorted newest-first."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the state store is reachable."""
