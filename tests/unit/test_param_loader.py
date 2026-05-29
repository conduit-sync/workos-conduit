from __future__ import annotations

import pytest

from src.core.param_loader import parameter_name_from_ssm_arn


def test_parameter_name_from_ssm_arn() -> None:
    arn = (
        "arn:aws:ssm:us-west-2:123456789012:parameter/"
        "stakesmfg/dev/workos-conduit/ninjaone-oauth-refresh-token"
    )
    assert parameter_name_from_ssm_arn(arn) == (
        "/stakesmfg/dev/workos-conduit/ninjaone-oauth-refresh-token"
    )


def test_parameter_name_from_ssm_arn_empty() -> None:
    assert parameter_name_from_ssm_arn("") == ""
    assert parameter_name_from_ssm_arn("   ") == ""


def test_parameter_name_from_ssm_arn_rejects_non_arn() -> None:
    with pytest.raises(ValueError, match="must be an SSM parameter ARN"):
        parameter_name_from_ssm_arn("/plain/path")


def test_parameter_name_from_ssm_arn_rejects_malformed_arn() -> None:
    with pytest.raises(ValueError, match="Invalid SSM parameter ARN"):
        parameter_name_from_ssm_arn("arn:aws:ssm:us-east-1:123456789012:foo/bar")
