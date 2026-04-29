from __future__ import annotations

from datetime import UTC, datetime

from src.backends.local.cursor_memory import MemoryCursorBackend
from src.core.models import RunRecord, RunStatus


def _make_record(run_id: str, offset: int = 0) -> RunRecord:
    from datetime import timedelta

    base = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC) + timedelta(seconds=offset)
    return RunRecord(
        run_id=run_id,
        adapter="ninjaone",
        started_at=base,
        finished_at=base,
        duration_seconds=1.0,
        status=RunStatus.SUCCESS,
        trigger_source="api",
        events_fetched=1,
        events_processed=1,
        cursor_before=None,
        cursor_after=run_id,
        results=[],
        errors=[],
    )


# ── MemoryCursorBackend ───────────────────────────────────────────────────────


def test_memory_cursor_starts_none():
    backend = MemoryCursorBackend()
    assert backend.get() is None


def test_memory_cursor_save_then_get():
    backend = MemoryCursorBackend()
    backend.save("evt_abc")
    assert backend.get() == "evt_abc"


def test_memory_cursor_save_twice_returns_latest():
    backend = MemoryCursorBackend()
    backend.save("evt_first")
    backend.save("evt_second")
    assert backend.get() == "evt_second"


def test_memory_cursor_health_check():
    assert MemoryCursorBackend().health_check() is True


# ── FileStateBackend ──────────────────────────────────────────────────────────


def test_file_state_write_and_get(tmp_path, settings_override):
    from src.backends.local.state_file import FileStateBackend

    settings_override = settings_override.model_copy(
        update={"local_state_dir": str(tmp_path), "state_backend": "local"}
    )
    backend = FileStateBackend(settings_override)

    record = _make_record("run-file-001")
    backend.write_run(record)

    found = backend.get_run("run-file-001")
    assert found is not None
    assert found.run_id == "run-file-001"


def test_file_state_get_missing_returns_none(tmp_path, settings_override):
    from src.backends.local.state_file import FileStateBackend

    settings_override = settings_override.model_copy(
        update={"local_state_dir": str(tmp_path), "state_backend": "local"}
    )
    backend = FileStateBackend(settings_override)
    assert backend.get_run("does-not-exist") is None


def test_file_state_list_sorted_desc(tmp_path, settings_override):
    from src.backends.local.state_file import FileStateBackend

    settings_override = settings_override.model_copy(
        update={"local_state_dir": str(tmp_path), "state_backend": "local"}
    )
    backend = FileStateBackend(settings_override)

    for i in range(5):
        backend.write_run(_make_record(f"run-{i:03d}", offset=i * 10))

    runs = backend.list_recent_runs(limit=5)
    assert len(runs) == 5
    assert runs[0].started_at >= runs[1].started_at


def test_file_state_list_respects_limit(tmp_path, settings_override):
    from src.backends.local.state_file import FileStateBackend

    settings_override = settings_override.model_copy(
        update={"local_state_dir": str(tmp_path), "state_backend": "local"}
    )
    backend = FileStateBackend(settings_override)

    for i in range(5):
        backend.write_run(_make_record(f"run-limit-{i}", offset=i))

    runs = backend.list_recent_runs(limit=2)
    assert len(runs) == 2


def test_file_state_health_check(tmp_path, settings_override):
    from src.backends.local.state_file import FileStateBackend

    settings_override = settings_override.model_copy(
        update={"local_state_dir": str(tmp_path), "state_backend": "local"}
    )
    backend = FileStateBackend(settings_override)
    assert backend.health_check() is True


def test_file_state_list_skips_corrupt_file(tmp_path, settings_override):
    from src.backends.local.state_file import FileStateBackend

    settings_override = settings_override.model_copy(
        update={"local_state_dir": str(tmp_path), "state_backend": "local"}
    )
    backend = FileStateBackend(settings_override)
    backend.write_run(_make_record("run-good"))

    # Write a corrupt JSON file into the runs dir
    runs_dir = tmp_path / "runs"
    (runs_dir / "corrupt.json").write_text("not json {{{")

    runs = backend.list_recent_runs(limit=10)
    assert len(runs) == 1
    assert runs[0].run_id == "run-good"
