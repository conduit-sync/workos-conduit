# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from typing import TYPE_CHECKING

from src.backends.aws.client import make_boto_client

if TYPE_CHECKING:
    from src.config import Settings

_SSM_PARAMETER_ARN_MARKER = ":parameter/"


def parameter_name_from_ssm_arn(arn: str) -> str:
    """Resolve an SSM parameter ARN to the Name used by boto3 APIs."""
    arn = arn.strip()
    if not arn:
        return ""
    if not arn.startswith("arn:"):
        raise ValueError(
            "NINJAONE_OAUTH_REFRESH_TOKEN_UPDATE_SSM_ARN must be an SSM parameter ARN"
        )
    idx = arn.find(_SSM_PARAMETER_ARN_MARKER)
    if idx == -1:
        raise ValueError(f"Invalid SSM parameter ARN: {arn!r}")
    name = arn[idx + len(_SSM_PARAMETER_ARN_MARKER) :]
    if not name.startswith("/"):
        name = f"/{name}"
    return name


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
