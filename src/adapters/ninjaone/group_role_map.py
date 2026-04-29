# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from src.config import Settings


def load_group_role_map(settings: Settings) -> dict[str, str]:
    """
    Loads the WorkOS-group → NinjaOne-role mapping from the configured source.

    source=env (default): reads NINJAONE_GROUP_ROLE_MAP env var (JSON string).
    source=ssm: reads a JSON string stored in SSM Parameter Store at
      NINJAONE_GROUP_ROLE_MAP_SSM_PARAM.  Fails fast at adapter startup if the
      parameter is missing or malformed, rather than silently skipping all groups.
    """
    if settings.ninjaone_group_role_map_source == "ssm":
        client = boto3.client("ssm", region_name=settings.aws_region)
        resp = client.get_parameter(Name=settings.ninjaone_group_role_map_ssm_param)
        raw = resp["Parameter"]["Value"]
    else:
        raw = settings.ninjaone_group_role_map

    return json.loads(raw)
