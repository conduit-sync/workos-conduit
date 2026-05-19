# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from botocore.exceptions import ClientError

from src.backends.aws.client import make_boto_client
from src.backends.base import CursorBackend

if TYPE_CHECKING:
    from src.config import Settings

log = structlog.get_logger()


class SsmCursorBackend(CursorBackend):
    def __init__(self, settings: Settings) -> None:
        self._client = make_boto_client("ssm", settings)
        self._param = settings.ssm_cursor_param

    def get(self) -> str | None:
        try:
            resp = self._client.get_parameter(Name=self._param)
            return resp["Parameter"]["Value"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ParameterNotFound":
                return None
            raise

    def save(self, event_id: str) -> None:
        self._client.put_parameter(
            Name=self._param,
            Value=event_id,
            Type="String",
            Overwrite=True,
        )
        log.debug("cursor_saved", event_id=event_id, cursor_backend="aws")

    def health_check(self) -> bool:
        try:
            self._client.describe_parameters(
                ParameterFilters=[{"Key": "Name", "Values": [self._param]}]
            )
            return True
        except Exception:
            return False
