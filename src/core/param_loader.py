# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from typing import TYPE_CHECKING

from src.backends.aws.client import make_boto_client

if TYPE_CHECKING:
    from src.config import Settings


def load_ssm_or_env(
    source: str,
    env_value: str,
    ssm_param: str,
    settings: Settings,
) -> str:
    """Return raw string value from SSM Parameter Store or the env fallback."""
    if source == "ssm":
        client = make_boto_client("ssm", settings)
        return client.get_parameter(Name=ssm_param)["Parameter"]["Value"]
    return env_value
