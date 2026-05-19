# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.backends.aws.client import make_boto_client
from src.backends.base import StateBackend
from src.core.models import RunRecord

if TYPE_CHECKING:
    from src.config import Settings

log = structlog.get_logger()


class S3StateBackend(StateBackend):
    def __init__(self, settings: Settings) -> None:
        if not settings.s3_state_bucket:
            raise ValueError("s3_state_bucket is required when state_backend=aws")
        self._client = make_boto_client("s3", settings)
        self._bucket = settings.s3_state_bucket
        self._prefix = settings.s3_state_prefix

    def write_run(self, record: RunRecord) -> str:
        dt = record.started_at
        key = (
            f"{self._prefix}"
            f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/"
            f"{record.run_id}.json"
        )
        body = record.model_dump_json().encode()
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        log.debug(
            "run_written_to_backend",
            s3_key=key,
            run_id=record.run_id,
            state_backend="aws",
        )
        return key

    def get_run(self, run_id: str) -> RunRecord | None:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            for obj in page.get("Contents", []):
                if run_id in obj["Key"]:
                    resp = self._client.get_object(Bucket=self._bucket, Key=obj["Key"])
                    return RunRecord.model_validate_json(resp["Body"].read())
        return None

    def list_recent_runs(self, limit: int) -> list[RunRecord]:
        paginator = self._client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))

        runs: list[RunRecord] = []
        for key in keys:
            try:
                resp = self._client.get_object(Bucket=self._bucket, Key=key)
                runs.append(RunRecord.model_validate_json(resp["Body"].read()))
            except Exception as exc:
                log.warning("failed_to_parse_run", key=key, error=str(exc))

        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]

    def health_check(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return True
        except Exception:
            return False
