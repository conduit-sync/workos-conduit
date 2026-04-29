from __future__ import annotations

import pytest

from src.backends.aws.cursor_ssm import SsmCursorBackend
from src.backends.aws.state_s3 import S3StateBackend
from src.backends.base import CursorBackend, StateBackend
from src.backends.registry import (
    get_cursor_backend,
    get_state_backend,
    register_cursor_backend,
    register_state_backend,
)


def test_get_cursor_backend_aws(settings_override):
    backend = get_cursor_backend("aws", settings_override)
    assert isinstance(backend, SsmCursorBackend)


def test_get_state_backend_aws(settings_override):
    backend = get_state_backend("aws", settings_override)
    assert isinstance(backend, S3StateBackend)


def test_unknown_cursor_backend_raises(settings_override):
    with pytest.raises(ValueError, match="Unknown cursor backend"):
        get_cursor_backend("nonexistent", settings_override)


def test_unknown_state_backend_raises(settings_override):
    with pytest.raises(ValueError, match="Unknown state backend"):
        get_state_backend("nonexistent", settings_override)


def test_custom_cursor_backend_resolvable(settings_override):
    class FakeCursor(CursorBackend):
        def get(self):
            return None

        def save(self, event_id):
            pass

        def health_check(self):
            return True

    register_cursor_backend("fake_cursor_test", lambda s: FakeCursor())
    backend = get_cursor_backend("fake_cursor_test", settings_override)
    assert isinstance(backend, FakeCursor)


def test_custom_state_backend_resolvable(settings_override):
    class FakeState(StateBackend):
        def write_run(self, record):
            return "key"

        def get_run(self, run_id):
            return None

        def list_recent_runs(self, limit):
            return []

        def health_check(self):
            return True

    register_state_backend("fake_state_test", lambda s: FakeState())
    backend = get_state_backend("fake_state_test", settings_override)
    assert isinstance(backend, FakeState)
