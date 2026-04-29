# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from src.backends.base import StateBackend

if TYPE_CHECKING:
    from src.config import Settings
    from src.core.models import RunRecord

log = structlog.get_logger()


class FileStateBackend(StateBackend):
    """
    Filesystem-backed state store for local development.
    Writes one JSON file per run under LOCAL_STATE_DIR (default: .local-state/runs/).
    """

    def __init__(self, settings: Settings) -> None:
        self._dir = Path(settings.local_state_dir) / "runs"
        self._dir.mkdir(parents=True, exist_ok=True)

    def write_run(self, record: RunRecord) -> str:
        path = self._dir / f"{record.run_id}.json"
        path.write_text(record.model_dump_json())
        log.debug("run_written", run_id=record.run_id, path=str(path))
        return str(path)

    def get_run(self, run_id: str) -> RunRecord | None:
        from src.core.models import RunRecord as RR

        path = self._dir / f"{run_id}.json"
        if not path.exists():
            return None
        return RR.model_validate_json(path.read_text())

    def list_recent_runs(self, limit: int) -> list[RunRecord]:
        from src.core.models import RunRecord as RR

        records = []
        for path in self._dir.glob("*.json"):
            try:
                records.append(RR.model_validate_json(path.read_text()))
            except Exception:
                log.warning("run_file_unreadable", path=str(path))
        records.sort(key=lambda r: r.started_at, reverse=True)
        return records[:limit]

    def health_check(self) -> bool:
        return self._dir.exists()
