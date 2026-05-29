from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

# Before importing Settings: skip developer .env and drop removed redirect env keys.
os.environ["WORKOS_CONDUIT_TESTING"] = "1"
for _obsolete in (
    "WORKOS_REDIRECT_URL_INTERNAL",
    "WORKOS_REDIRECT_URL_EASTLAKE",
    "NINJAONE_REDIRECT_URL_INTERNAL",
    "NINJAONE_REDIRECT_URL_EASTLAKE",
    "WORKOS_SSO_DEFAULT_REALM",
    "WORKOS_SSO_INTERNAL_ORG_REDIRECT_URI",
    "WORKOS_DASHBOARD_SSO_REDIRECT_URI",
    "WORKOS_SSO_REDIRECT_URI",
    "DASHBOARD_PUBLIC_BASE_URL",
):
    os.environ.pop(_obsolete, None)

_TEST_ENV_BOOTSTRAP = {
    "WORKOS_SSO_INTERNAL_ORG_API_KEY": "sk_test_key",
    "WORKOS_DIRECTORY_ID": "directory_test",
    "SYNC_TARGET_ADAPTER": "ninjaone",
    "NINJAONE_OAUTH_CLIENT_ID": "test-client-id",
    "NINJAONE_OAUTH_CLIENT_SECRET": "test-client-secret",
    "CURSOR_BACKEND": "aws",
    "STATE_BACKEND": "aws",
    "S3_STATE_BUCKET": "test-bucket",
    "API_SECRET_KEY": "test-secret-key",
    "NINJAONE_GROUP_ROLE_MAP": "{}",
    "LOG_OUTPUT": "stdout",
    "LOG_FORMAT": "console",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
}
for _key, _value in _TEST_ENV_BOOTSTRAP.items():
    os.environ.setdefault(_key, _value)

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from src.config import Settings, get_settings
from src.core.models import RunRecord, RunStatus

FIXTURES = Path(__file__).parent / "fixtures"

_OBSOLETE_ENV_KEYS = (
    "WORKOS_REDIRECT_URL_INTERNAL",
    "WORKOS_REDIRECT_URL_EASTLAKE",
    "NINJAONE_REDIRECT_URL_INTERNAL",
    "NINJAONE_REDIRECT_URL_EASTLAKE",
    "WORKOS_SSO_DEFAULT_REALM",
    "WORKOS_SSO_INTERNAL_ORG_REDIRECT_URI",
    "WORKOS_DASHBOARD_SSO_REDIRECT_URI",
    "WORKOS_SSO_REDIRECT_URI",
    "DASHBOARD_PUBLIC_BASE_URL",
)

_TEST_ENV = _TEST_ENV_BOOTSTRAP


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch):
    """Set required env vars and clear the lru_cache so each test gets fresh Settings."""
    for key in _OBSOLETE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings_override() -> Settings:
    """Returns Settings with all required fields set to safe test values."""
    return Settings(
        workos_sso_internal_org_api_key="sk_test_key",
        workos_directory_id="directory_test",
        sync_target_adapter="ninjaone",
        ninjaone_oauth_client_id="test-client-id",
        ninjaone_oauth_client_secret="test-client-secret",
        cursor_backend="aws",
        state_backend="aws",
        s3_state_bucket="test-bucket",
        api_secret_key="test-secret-key",
        log_output="stdout",
        log_format="console",
    )


@pytest.fixture
def test_client(settings_override: Settings) -> TestClient:
    """FastAPI TestClient with settings dependency overridden."""
    from src.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_override

    from src import deps

    app.dependency_overrides[deps.get_settings] = lambda: settings_override

    with TestClient(app) as client:
        yield client


@pytest.fixture
def aws_credentials(monkeypatch):
    """Sets fake AWS credentials so moto works without real creds."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def mock_s3(aws_credentials):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        yield s3


@pytest.fixture
def mock_ssm(aws_credentials):
    with mock_aws():
        yield boto3.client("ssm", region_name="us-east-1")


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def workos_user_created_event() -> dict:
    return _load_fixture("workos_user_created.json")


@pytest.fixture
def workos_user_updated_event() -> dict:
    return _load_fixture("workos_user_updated.json")


@pytest.fixture
def workos_user_deleted_event() -> dict:
    return _load_fixture("workos_user_deleted.json")


@pytest.fixture
def workos_group_user_added_event() -> dict:
    return _load_fixture("workos_group_user_added.json")


@pytest.fixture
def workos_group_user_removed_event() -> dict:
    return _load_fixture("workos_group_user_removed.json")


def _make_run_record(run_id: str, offset_seconds: int = 0) -> RunRecord:
    now = datetime(2024, 4, 1, 12, 0, 0, tzinfo=UTC)
    from datetime import timedelta

    started = now + timedelta(seconds=offset_seconds)
    finished = started + timedelta(seconds=1)
    return RunRecord(
        run_id=run_id,
        adapter="ninjaone",
        started_at=started,
        finished_at=finished,
        duration_seconds=1.0,
        status=RunStatus.SUCCESS,
        trigger_source="api",
        events_fetched=1,
        events_processed=1,
        cursor_before=None,
        cursor_after=run_id,
        results=[],
        errors=[],
    )


@pytest.fixture
def sample_run_records(mock_s3, settings_override: Settings) -> list[RunRecord]:
    """Seeds 5 RunRecord objects into mock S3, returns sorted most-recent-first."""
    from src.backends.aws.state_s3 import S3StateBackend

    backend = S3StateBackend(settings_override)
    records = [
        _make_run_record(f"run-{i:04d}", offset_seconds=i * 10) for i in range(5)
    ]
    for rec in records:
        backend.write_run(rec)
    return sorted(records, key=lambda r: r.started_at, reverse=True)
