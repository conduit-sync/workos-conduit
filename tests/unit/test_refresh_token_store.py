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


@mock_aws
def test_runtime_rotation_mirrors_to_update_param_when_configured(settings_override):
    update_path = "/workos-conduit/ninjaone/oauth-refresh-token-active"
    update_arn = (
        "arn:aws:ssm:us-east-1:123456789012:parameter/"
        "workos-conduit/ninjaone/oauth-refresh-token-active"
    )
    ssm = boto3.client("ssm", region_name="us-east-1")
    settings = settings_override.model_copy(
        update={"ninjaone_oauth_refresh_token_update_ssm_arn": update_arn}
    )
    store = SsmRefreshTokenStore(settings)

    record = RefreshTokenRecord.from_refresh_token(
        refresh_token="rotated",
        scope="control offline_access monitoring management",
        lifetime_days=30,
        issuer="runtime",
    )
    store.put(record)

    mirrored = ssm.get_parameter(Name=update_path, WithDecryption=True)["Parameter"][
        "Value"
    ]
    assert "rotated" in mirrored

    primary = ssm.get_parameter(
        Name=settings.ninjaone_oauth_refresh_token_ssm_param, WithDecryption=True
    )["Parameter"]["Value"]
    assert "rotated" in primary


@mock_aws
def test_runtime_rotation_skips_update_param_when_not_configured(settings_override):
    ssm = boto3.client("ssm", region_name="us-east-1")
    store = SsmRefreshTokenStore(settings_override)

    record = RefreshTokenRecord.from_refresh_token(
        refresh_token="rotated",
        scope="control offline_access monitoring management",
        lifetime_days=30,
        issuer="runtime",
    )
    store.put(record)

    params = {p["Name"] for p in ssm.describe_parameters()["Parameters"]}
    assert settings_override.ninjaone_oauth_refresh_token_ssm_param in params
    assert len(params) == 1


@mock_aws
def test_dashboard_bootstrap_does_not_mirror_to_update_param(settings_override):
    update_path = "/workos-conduit/ninjaone/oauth-refresh-token-active"
    update_arn = (
        "arn:aws:ssm:us-east-1:123456789012:parameter/"
        "workos-conduit/ninjaone/oauth-refresh-token-active"
    )
    ssm = boto3.client("ssm", region_name="us-east-1")
    settings = settings_override.model_copy(
        update={"ninjaone_oauth_refresh_token_update_ssm_arn": update_arn}
    )
    store = SsmRefreshTokenStore(settings)

    record = RefreshTokenRecord.from_refresh_token(
        refresh_token="bootstrap",
        scope="control offline_access monitoring management",
        lifetime_days=30,
        issuer="dashboard",
    )
    store.put(record)

    params = {p["Name"] for p in ssm.describe_parameters()["Parameters"]}
    assert update_path not in params
    assert settings.ninjaone_oauth_refresh_token_ssm_param in params
