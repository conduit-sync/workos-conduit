# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from src.core.param_loader import load_ssm_or_env

if TYPE_CHECKING:
    from src.config import Settings

log = structlog.get_logger()


@dataclass
class OrgGroupMapping:
    ninjaone_organization_name: str
    ninjaone_organization_id: int
    google_workspace_group_name: str
    ninjaone_role: str


def load_group_role_map(settings: Settings) -> dict[str, OrgGroupMapping]:
    """
    Loads the WorkOS-group → NinjaOne org+role mapping from the configured source.

    source=env (default): reads NINJAONE_GROUP_ROLE_MAP env var (JSON string).
    source=ssm: reads a JSON string stored in SSM Parameter Store at
      NINJAONE_GROUP_ROLE_MAP_SSM_PARAM.

    Expected JSON format:
    {
      "organizations_groups_mapping": [
        {
          "ninjaone_organization_name": "Acme Corp",
          "ninjaone_organization_id": 12345,
          "google_workspace_group_name": "acme-users",
          "ninjaone_role": "END_USER"
        }
      ]
    }
    """
    raw = load_ssm_or_env(
        source=settings.ninjaone_group_role_map_source,
        env_value=settings.ninjaone_group_role_map,
        ssm_param=settings.ninjaone_group_role_map_ssm_param,
        settings=settings,
    )
    data = json.loads(raw)
    entries = data.get("organizations_groups_mapping", [])
    result: dict[str, OrgGroupMapping] = {}
    for entry in entries:
        mapping = OrgGroupMapping(
            ninjaone_organization_name=entry["ninjaone_organization_name"],
            ninjaone_organization_id=int(entry["ninjaone_organization_id"]),
            google_workspace_group_name=entry["google_workspace_group_name"],
            ninjaone_role=entry["ninjaone_role"],
        )
        result[mapping.google_workspace_group_name] = mapping

    if result:
        log.debug(
            "group_role_map_loaded",
            source=settings.ninjaone_group_role_map_source,
            groups=list(result.keys()),
        )
    else:
        log.warning(
            "group_role_map_empty",
            source=settings.ninjaone_group_role_map_source,
            detail="No group→org mappings found; group membership events will be skipped",
        )
    return result
