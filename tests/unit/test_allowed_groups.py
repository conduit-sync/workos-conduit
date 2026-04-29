from __future__ import annotations

import json

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from src.config import Settings
from src.core.allowed_groups import load_allowed_groups

_BASE = dict(
    workos_api_key="sk_test",
    workos_directory_id="dir_test",
    ninjaone_client_id="cid",
    ninjaone_client_secret="csecret",
    s3_state_bucket="test-bucket",
)


def _settings(**kwargs) -> Settings:
    return Settings(**{**_BASE, **kwargs})


# ---------------------------------------------------------------------------
# source=env (default)
# ---------------------------------------------------------------------------


def test_load_from_env_returns_parsed_list():
    s = _settings(sync_allowed_groups='["IT Admins", "Support Team"]')
    assert load_allowed_groups(s) == ["IT Admins", "Support Team"]


def test_load_from_env_empty_array_returns_empty_list():
    s = _settings(sync_allowed_groups="[]")
    assert load_allowed_groups(s) == []


def test_load_from_env_invalid_json_raises():
    s = _settings(sync_allowed_groups="not-json")
    with pytest.raises(json.JSONDecodeError):
        load_allowed_groups(s)


# ---------------------------------------------------------------------------
# source=ssm
# ---------------------------------------------------------------------------


@mock_aws
def test_load_from_ssm_returns_parsed_list():
    boto3.client("ssm", region_name="us-east-1").put_parameter(
        Name="/workos-conduit/allowed-groups",
        Value='["DevOps", "IT Admins"]',
        Type="String",
    )
    s = _settings(sync_allowed_groups_source="ssm")
    assert load_allowed_groups(s) == ["DevOps", "IT Admins"]


@mock_aws
def test_load_from_ssm_custom_param_name():
    boto3.client("ssm", region_name="us-east-1").put_parameter(
        Name="/custom/allowed",
        Value='["Engineering"]',
        Type="String",
    )
    s = _settings(
        sync_allowed_groups_source="ssm",
        sync_allowed_groups_ssm_param="/custom/allowed",
    )
    assert load_allowed_groups(s) == ["Engineering"]


@mock_aws
def test_load_from_ssm_param_not_found_raises():
    s = _settings(sync_allowed_groups_source="ssm")
    with pytest.raises(ClientError) as exc_info:
        load_allowed_groups(s)
    assert exc_info.value.response["Error"]["Code"] == "ParameterNotFound"


@mock_aws
def test_load_from_ssm_invalid_json_raises():
    boto3.client("ssm", region_name="us-east-1").put_parameter(
        Name="/workos-conduit/allowed-groups",
        Value="not-valid-json",
        Type="String",
    )
    s = _settings(sync_allowed_groups_source="ssm")
    with pytest.raises(json.JSONDecodeError):
        load_allowed_groups(s)
