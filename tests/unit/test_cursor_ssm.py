from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from src.backends.aws.cursor_ssm import SsmCursorBackend
from src.config import Settings


@pytest.fixture
def settings(settings_override: Settings) -> Settings:
    return settings_override


@mock_aws
def test_get_before_any_save_returns_none(settings):
    boto3.client("ssm", region_name="us-east-1")
    backend = SsmCursorBackend(settings)
    assert backend.get() is None


@mock_aws
def test_save_then_get_returns_value(settings):
    backend = SsmCursorBackend(settings)
    backend.save("evt_001")
    assert backend.get() == "evt_001"


@mock_aws
def test_save_twice_get_returns_latest(settings):
    backend = SsmCursorBackend(settings)
    backend.save("evt_001")
    backend.save("evt_002")
    assert backend.get() == "evt_002"


@mock_aws
def test_health_check_returns_true(settings):
    backend = SsmCursorBackend(settings)
    assert backend.health_check() is True
