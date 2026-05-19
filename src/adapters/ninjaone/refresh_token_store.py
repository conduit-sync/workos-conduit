# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError

from src.backends.aws.client import make_boto_client


class RefreshTokenRecord(BaseModel):
    refresh_token: str
    generated_at: datetime
    expires_at: datetime
    scope: str
    issuer: Literal["dashboard", "cli", "runtime"]

    @classmethod
    def from_refresh_token(
        cls,
        refresh_token: str,
        scope: str,
        lifetime_days: int,
        issuer: Literal["dashboard", "cli", "runtime"],
    ) -> RefreshTokenRecord:
        generated_at = datetime.now(tz=UTC)
        expires_at = generated_at + timedelta(days=lifetime_days)
        return cls(
            refresh_token=refresh_token,
            generated_at=generated_at,
            expires_at=expires_at,
            scope=scope,
            issuer=issuer,
        )


class RefreshTokenStore(Protocol):
    def get(self) -> RefreshTokenRecord | None: ...

    def put(self, record: RefreshTokenRecord) -> None: ...


@dataclass
class InMemoryRefreshTokenStore:
    _record: RefreshTokenRecord | None = None

    def get(self) -> RefreshTokenRecord | None:
        return self._record

    def put(self, record: RefreshTokenRecord) -> None:
        self._record = record


class SsmRefreshTokenStore:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._client = make_boto_client("ssm", settings)
        self._param = settings.ninjaone_oauth_refresh_token_ssm_param

    def get(self) -> RefreshTokenRecord | None:
        try:
            response = self._client.get_parameter(Name=self._param, WithDecryption=True)
        except self._client.exceptions.ParameterNotFound:
            return None

        raw = response["Parameter"]["Value"]
        raw = raw.strip()
        if not raw:
            return None

        # Backward compatibility: older deployments may have stored just the raw
        # refresh token string in SSM instead of the JSON envelope.
        if not raw.startswith("{"):
            return RefreshTokenRecord.from_refresh_token(
                refresh_token=raw,
                scope="",
                lifetime_days=self._settings.ninjaone_oauth_refresh_token_lifetime_days,
                issuer="runtime",
            )

        data = json.loads(raw)
        try:
            return RefreshTokenRecord.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"Invalid refresh token payload in SSM '{self._param}'"
            ) from exc

    def put(self, record: RefreshTokenRecord) -> None:
        self._client.put_parameter(
            Name=self._param,
            Value=record.model_dump_json(),
            Type="SecureString",
            Overwrite=True,
        )
