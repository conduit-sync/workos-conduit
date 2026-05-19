from __future__ import annotations

import boto3
from moto import mock_aws

from src.adapters.ninjaone.refresh_token_store import (
    RefreshTokenRecord,
    SsmRefreshTokenStore,
)


@mock_aws
def test_ssm_refresh_token_store_round_trip(settings_override):
    ssm = boto3.client("ssm", region_name="us-east-1")
    store = SsmRefreshTokenStore(settings_override)

    record = RefreshTokenRecord.from_refresh_token(
        refresh_token="rtok",
        scope="control offline_access monitoring management",
        lifetime_days=30,
        issuer="cli",
    )
    store.put(record)

    loaded = store.get()
    assert loaded is not None
    assert loaded.refresh_token == "rtok"
    assert loaded.scope == "control offline_access monitoring management"
    assert loaded.issuer == "cli"

    params = ssm.describe_parameters()["Parameters"]
    assert any(
        p["Name"] == settings_override.ninjaone_oauth_refresh_token_ssm_param
        for p in params
    )
