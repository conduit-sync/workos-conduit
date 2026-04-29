# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from src.adapters.base import BaseTargetAdapter

if TYPE_CHECKING:
    from src.config import Settings

_REGISTRY: dict[str, Callable[[Settings], BaseTargetAdapter]] = {}


def register_adapter(
    key: str, factory: Callable[[Settings], BaseTargetAdapter]
) -> None:
    _REGISTRY[key] = factory


def get_adapter(key: str, settings: Settings) -> BaseTargetAdapter:
    if key not in _REGISTRY:
        raise ValueError(
            f"Unknown adapter '{key}'. "
            f"Available: {list(_REGISTRY.keys())}. "
            "See CONTRIBUTING.md to add a new adapter."
        )
    return _REGISTRY[key](settings)


# Register built-in adapters
from src.adapters.ninjaone.adapter import NinjaOneAdapter  # noqa: E402

register_adapter("ninjaone", lambda s: NinjaOneAdapter(s))
