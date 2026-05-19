from __future__ import annotations

import pytest

from src.adapters.ninjaone.adapter import NinjaOneAdapter
from src.backends.aws.state_s3 import S3StateBackend
from src.config import Settings


def _base(**kwargs) -> dict:
    defaults = dict(
        workos_api_key="sk_test",
        workos_directory_id="directory_test",
        ninjaone_oauth_client_id="test-client-id",
        ninjaone_oauth_client_secret="test-client-secret",
        state_backend="local",
        cursor_backend="local",
    )
    return {**defaults, **kwargs}


def test_valid_settings_constructs():
    s = Settings(**_base())
    assert s.workos_api_key == "sk_test"


@pytest.mark.parametrize(
    ("field", "error_match"),
    [
        ("ninjaone_oauth_client_id", "ninjaone_oauth_client_id"),
        ("ninjaone_oauth_client_secret", "ninjaone_oauth_client_secret"),
    ],
)
def test_missing_ninjaone_oauth_credential_raises(field: str, error_match: str):
    # Validation lives in NinjaOneAdapter.__init__ (OCP — Settings no longer knows adapters)
    settings = Settings(**_base(**{field: ""}))
    with pytest.raises(ValueError, match=error_match):
        NinjaOneAdapter(settings)


def test_aws_state_backend_requires_s3_bucket(settings_override):
    # Validation moved to S3StateBackend.__init__ (OCP — Settings no longer knows backends)
    settings = settings_override.model_copy(update={"s3_state_bucket": ""})
    with pytest.raises(ValueError, match="s3_state_bucket"):
        S3StateBackend(settings)


def test_ssm_role_map_source_requires_param():
    with pytest.raises(ValueError, match="ninjaone_group_role_map_ssm_param"):
        Settings(
            **_base(
                ninjaone_group_role_map_source="ssm",
                ninjaone_group_role_map_ssm_param="",
            )
        )


def test_invalid_json_event_types_raises():
    with pytest.raises(ValueError, match="workos_event_types"):
        Settings(**_base(workos_event_types='["unclosed'))


def test_comma_separated_event_types_does_not_raise():
    s = Settings(**_base(workos_event_types="dsync.user.created,dsync.user.updated"))
    assert "dsync.user.created" in s.workos_event_types
