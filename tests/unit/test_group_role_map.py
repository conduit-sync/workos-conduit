from __future__ import annotations

import json
import os

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from src.adapters.ninjaone.group_role_map import OrgGroupMapping, load_group_role_map
from src.config import Settings

_BASE = {
    "workos_api_key": "sk_test",
    "workos_directory_id": "dir_test",
    "ninjaone_oauth_client_id": "test-client-id",
    "ninjaone_oauth_client_secret": "test-client-secret",
    "s3_state_bucket": "test-bucket",
}

_MAPPING_JSON = json.dumps(
    {
        "organizations_groups_mapping": [
            {
                "ninjaone_organization_name": "Acme Corp",
                "ninjaone_organization_id": 111,
                "google_workspace_group_name": "acme-users",
                "ninjaone_role": "END_USER",
            }
        ]
    }
)

_MULTI_MAPPING_JSON = json.dumps(
    {
        "organizations_groups_mapping": [
            {
                "ninjaone_organization_name": "Acme Corp",
                "ninjaone_organization_id": 111,
                "google_workspace_group_name": "acme-users",
                "ninjaone_role": "END_USER",
            },
            {
                "ninjaone_organization_name": "Beta LLC",
                "ninjaone_organization_id": 222,
                "google_workspace_group_name": "beta-users",
                "ninjaone_role": "END_USER",
            },
        ]
    }
)


def _settings(**kwargs) -> Settings:
    return Settings(**{**_BASE, **kwargs})


def test_load_from_env_returns_org_group_mapping():
    s = _settings(ninjaone_group_role_map=_MAPPING_JSON)
    result = load_group_role_map(s)
    assert "acme-users" in result
    m = result["acme-users"]
    assert isinstance(m, OrgGroupMapping)
    assert m.ninjaone_organization_id == 111
    assert m.ninjaone_organization_name == "Acme Corp"
    assert m.ninjaone_role == "END_USER"
    assert m.google_workspace_group_name == "acme-users"


def test_load_from_env_multiple_mappings():
    s = _settings(ninjaone_group_role_map=_MULTI_MAPPING_JSON)
    result = load_group_role_map(s)
    assert set(result.keys()) == {"acme-users", "beta-users"}
    assert result["beta-users"].ninjaone_organization_id == 222


def test_load_from_env_empty_list():
    s = _settings(ninjaone_group_role_map='{"organizations_groups_mapping": []}')
    assert load_group_role_map(s) == {}


def test_load_from_env_invalid_json_raises():
    s = _settings(ninjaone_group_role_map="not-json")
    with pytest.raises(json.JSONDecodeError):
        load_group_role_map(s)


@mock_aws
def test_load_from_ssm_returns_org_group_mapping():
    boto3.client("ssm", region_name=os.environ["AWS_DEFAULT_REGION"]).put_parameter(
        Name="/workos-conduit/ninjaone/group-role-map",
        Value=_MAPPING_JSON,
        Type="String",
    )
    s = _settings(ninjaone_group_role_map_source="ssm")
    result = load_group_role_map(s)
    assert "acme-users" in result
    assert result["acme-users"].ninjaone_organization_id == 111


@mock_aws
def test_load_from_ssm_custom_param_name():
    boto3.client("ssm", region_name=os.environ["AWS_DEFAULT_REGION"]).put_parameter(
        Name="/custom/path",
        Value=_MAPPING_JSON,
        Type="String",
    )
    s = _settings(
        ninjaone_group_role_map_source="ssm",
        ninjaone_group_role_map_ssm_param="/custom/path",
    )
    result = load_group_role_map(s)
    assert "acme-users" in result


@mock_aws
def test_load_from_ssm_param_not_found_raises():
    s = _settings(ninjaone_group_role_map_source="ssm")
    with pytest.raises(ClientError) as exc_info:
        load_group_role_map(s)
    assert exc_info.value.response["Error"]["Code"] == "ParameterNotFound"


@mock_aws
def test_load_from_ssm_invalid_json_raises():
    boto3.client("ssm", region_name=os.environ["AWS_DEFAULT_REGION"]).put_parameter(
        Name="/workos-conduit/ninjaone/group-role-map",
        Value="not-valid-json",
        Type="String",
    )
    s = _settings(ninjaone_group_role_map_source="ssm")
    with pytest.raises(json.JSONDecodeError):
        load_group_role_map(s)
