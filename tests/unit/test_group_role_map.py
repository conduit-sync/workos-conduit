from __future__ import annotations

import json

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from src.adapters.ninjaone.group_role_map import load_group_role_map
from src.config import Settings

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


def test_load_from_env_returns_parsed_map():
    s = _settings(ninjaone_group_role_map='{"IT Admins": "administrator"}')
    assert load_group_role_map(s) == {"IT Admins": "administrator"}


def test_load_from_env_empty_map():
    s = _settings(ninjaone_group_role_map="{}")
    assert load_group_role_map(s) == {}


def test_load_from_env_invalid_json_raises():
    s = _settings(ninjaone_group_role_map="not-json")
    with pytest.raises(json.JSONDecodeError):
        load_group_role_map(s)


# ---------------------------------------------------------------------------
# source=ssm
# ---------------------------------------------------------------------------


@mock_aws
def test_load_from_ssm_returns_parsed_map():
    boto3.client("ssm", region_name="us-east-1").put_parameter(
        Name="/workos-conduit/ninjaone/group-role-map",
        Value='{"DevOps": "senior_technician"}',
        Type="String",
    )
    s = _settings(ninjaone_group_role_map_source="ssm")
    assert load_group_role_map(s) == {"DevOps": "senior_technician"}


@mock_aws
def test_load_from_ssm_custom_param_name():
    boto3.client("ssm", region_name="us-east-1").put_parameter(
        Name="/custom/path",
        Value='{"A": "b"}',
        Type="String",
    )
    s = _settings(
        ninjaone_group_role_map_source="ssm",
        ninjaone_group_role_map_ssm_param="/custom/path",
    )
    assert load_group_role_map(s) == {"A": "b"}


@mock_aws
def test_load_from_ssm_param_not_found_raises():
    s = _settings(ninjaone_group_role_map_source="ssm")
    with pytest.raises(ClientError) as exc_info:
        load_group_role_map(s)
    assert exc_info.value.response["Error"]["Code"] == "ParameterNotFound"


@mock_aws
def test_load_from_ssm_invalid_json_raises():
    boto3.client("ssm", region_name="us-east-1").put_parameter(
        Name="/workos-conduit/ninjaone/group-role-map",
        Value="not-valid-json",
        Type="String",
    )
    s = _settings(ninjaone_group_role_map_source="ssm")
    with pytest.raises(json.JSONDecodeError):
        load_group_role_map(s)
