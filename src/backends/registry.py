# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from src.backends.base import CursorBackend, StateBackend

if TYPE_CHECKING:
    from src.config import Settings

_CURSOR_REGISTRY: dict[str, Callable[[Settings], CursorBackend]] = {}
_STATE_REGISTRY: dict[str, Callable[[Settings], StateBackend]] = {}


def register_cursor_backend(
    key: str, factory: Callable[[Settings], CursorBackend]
) -> None:
    _CURSOR_REGISTRY[key] = factory


def register_state_backend(
    key: str, factory: Callable[[Settings], StateBackend]
) -> None:
    _STATE_REGISTRY[key] = factory


def get_cursor_backend(key: str, settings: Settings) -> CursorBackend:
    if key not in _CURSOR_REGISTRY:
        raise ValueError(
            f"Unknown cursor backend '{key}'. "
            f"Available: {list(_CURSOR_REGISTRY.keys())}. "
            "See CONTRIBUTING.md to add a new backend."
        )
    return _CURSOR_REGISTRY[key](settings)


def get_state_backend(key: str, settings: Settings) -> StateBackend:
    if key not in _STATE_REGISTRY:
        raise ValueError(
            f"Unknown state backend '{key}'. "
            f"Available: {list(_STATE_REGISTRY.keys())}. "
            "See CONTRIBUTING.md to add a new backend."
        )
    return _STATE_REGISTRY[key](settings)


# AWS backends
from src.backends.aws.cursor_ssm import SsmCursorBackend  # noqa: E402
from src.backends.aws.state_s3 import S3StateBackend  # noqa: E402

register_cursor_backend("aws", lambda s: SsmCursorBackend(s))
register_state_backend("aws", lambda s: S3StateBackend(s))

# Local backends (for development — no AWS credentials required)
from src.backends.local.cursor_file import FileCursorBackend  # noqa: E402
from src.backends.local.cursor_memory import MemoryCursorBackend  # noqa: E402
from src.backends.local.state_file import FileStateBackend  # noqa: E402

register_cursor_backend("local", lambda s: FileCursorBackend(s))
register_cursor_backend("memory", lambda s: MemoryCursorBackend())
register_state_backend("local", lambda s: FileStateBackend(s))
