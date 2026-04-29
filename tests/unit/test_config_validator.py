from __future__ import annotations

import pytest

from src.config import Settings


def _base(**kwargs) -> dict:
    defaults = dict(
        workos_api_key="sk_test",
        workos_directory_id="directory_test",
        ninjaone_client_id="cid",
        ninjaone_client_secret="csecret",
        state_backend="local",
        cursor_backend="local",
    )
    return {**defaults, **kwargs}


def test_valid_settings_constructs():
    s = Settings(**_base())
    assert s.workos_api_key == "sk_test"


def test_missing_ninjaone_creds_raises():
    with pytest.raises(ValueError, match="ninjaone_client_id"):
        Settings(**_base(ninjaone_client_id="", ninjaone_client_secret=""))


def test_aws_state_backend_requires_s3_bucket():
    with pytest.raises(ValueError, match="s3_state_bucket"):
        Settings(**_base(state_backend="aws", s3_state_bucket=""))


def test_ssm_role_map_source_requires_param():
    with pytest.raises(ValueError, match="ninjaone_group_role_map_ssm_param"):
        Settings(
            **_base(
                ninjaone_group_role_map_source="ssm",
                ninjaone_group_role_map_ssm_param="",
            )
        )


def test_ssm_allowed_groups_source_requires_param():
    with pytest.raises(ValueError, match="sync_allowed_groups_ssm_param"):
        Settings(
            **_base(
                sync_allowed_groups_source="ssm",
                sync_allowed_groups_ssm_param="",
            )
        )


def test_invalid_json_event_types_raises():
    with pytest.raises(ValueError, match="workos_event_types"):
        Settings(**_base(workos_event_types='["unclosed'))


def test_comma_separated_event_types_does_not_raise():
    s = Settings(**_base(workos_event_types="dsync.user.created,dsync.user.updated"))
    assert "dsync.user.created" in s.workos_event_types
