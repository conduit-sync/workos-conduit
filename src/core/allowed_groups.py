# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from src.config import Settings


def load_allowed_groups(settings: Settings) -> list[str]:
    """
    Loads the group allow-list from the configured source.

    source=env (default): reads SYNC_ALLOWED_GROUPS env var (JSON array string).
      e.g. SYNC_ALLOWED_GROUPS='["IT Admins", "Support Team"]'
    source=ssm: reads a JSON array stored in SSM Parameter Store at
      SYNC_ALLOWED_GROUPS_SSM_PARAM.  Fails fast if the parameter is missing
      or malformed rather than silently allowing all groups.

    Returns [] (allow all groups through) if the value is an empty array.
    Raises json.JSONDecodeError on malformed JSON.
    Raises botocore.exceptions.ClientError on SSM failure.
    """
    if settings.sync_allowed_groups_source == "ssm":
        client = boto3.client("ssm", region_name=settings.aws_region)
        resp = client.get_parameter(Name=settings.sync_allowed_groups_ssm_param)
        raw = resp["Parameter"]["Value"]
    else:
        raw = settings.sync_allowed_groups
    return json.loads(raw)
