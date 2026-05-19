from __future__ import annotations

from src.backends.local.cursor_file import FileCursorBackend
from src.backends.local.cursor_memory import MemoryCursorBackend
from src.backends.local.state_file import FileStateBackend
from src.backends.registry import get_cursor_backend, get_state_backend


def test_local_cursor_backend_resolves(settings_override, tmp_path):
    settings_override = settings_override.model_copy(
        update={"cursor_backend": "local", "local_state_dir": str(tmp_path)}
    )
    backend = get_cursor_backend("local", settings_override)
    assert isinstance(backend, FileCursorBackend)


def test_memory_cursor_backend_resolves(settings_override, tmp_path):
    settings_override = settings_override.model_copy(
        update={"cursor_backend": "memory", "local_state_dir": str(tmp_path)}
    )
    backend = get_cursor_backend("memory", settings_override)
    assert isinstance(backend, MemoryCursorBackend)


def test_local_state_backend_resolves(settings_override, tmp_path):
    settings_override = settings_override.model_copy(
        update={"state_backend": "local", "local_state_dir": str(tmp_path)}
    )
    backend = get_state_backend("local", settings_override)
    assert isinstance(backend, FileStateBackend)
