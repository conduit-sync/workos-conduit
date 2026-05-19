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
        ts = record.started_at.strftime("%Y%m%d%H%M%S")
        path = self._dir / f"{ts}_{record.run_id[:8]}.json"
        path.write_text(record.model_dump_json())
        log.debug("run_written", run_id=record.run_id, path=str(path))
        return str(path)

    def get_run(self, run_id: str) -> RunRecord | None:
        from src.core.models import RunRecord as RR

        for path in self._dir.glob(f"*_{run_id[:8]}.json"):
            record = RR.model_validate_json(path.read_text())
            if record.run_id == run_id:
                return record
        return None

    def list_recent_runs(self, limit: int) -> list[RunRecord]:
        from src.core.models import RunRecord as RR

        paths = sorted(self._dir.glob("*.json"), reverse=True)
        records = []
        for path in paths[:limit]:
            try:
                records.append(RR.model_validate_json(path.read_text()))
            except Exception:
                log.warning("run_file_unreadable", path=str(path))
        return records

    def health_check(self) -> bool:
        return self._dir.exists()
