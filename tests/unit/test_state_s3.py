from __future__ import annotations

from datetime import UTC, datetime

import boto3
from moto import mock_aws

from src.backends.aws.state_s3 import S3StateBackend
from src.config import Settings
from src.core.models import RunRecord, RunStatus


def _make_record(run_id: str) -> RunRecord:
    now = datetime(2024, 4, 1, 12, 0, 0, tzinfo=UTC)
    return RunRecord(
        run_id=run_id,
        adapter="ninjaone",
        started_at=now,
        finished_at=now,
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


@mock_aws
def test_write_run_object_exists(settings_override: Settings):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3StateBackend(settings_override)
    record = _make_record("run-abc123")
    key = backend.write_run(record)
    assert "run-abc123" in key
    # Verify the object exists
    s3 = boto3.client("s3", region_name="us-east-1")
    obj = s3.get_object(Bucket="test-bucket", Key=key)
    assert obj["Body"].read()


@mock_aws
def test_write_two_runs_both_exist(settings_override: Settings):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3StateBackend(settings_override)
    backend.write_run(_make_record("run-001"))
    backend.write_run(_make_record("run-002"))
    runs = backend.list_recent_runs(limit=10)
    run_ids = {r.run_id for r in runs}
    assert "run-001" in run_ids
    assert "run-002" in run_ids


@mock_aws
def test_list_recent_runs_sorted_desc(settings_override: Settings):
    from datetime import timedelta

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3StateBackend(settings_override)
    base = datetime(2024, 4, 1, 12, 0, 0, tzinfo=UTC)
    for i in range(10):
        record = RunRecord(
            run_id=f"run-{i:03d}",
            adapter="ninjaone",
            started_at=base + timedelta(seconds=i),
            finished_at=base + timedelta(seconds=i + 1),
            duration_seconds=1.0,
            status=RunStatus.SUCCESS,
            trigger_source="api",
            events_fetched=1,
            events_processed=1,
            cursor_before=None,
            cursor_after=None,
            results=[],
            errors=[],
        )
        backend.write_run(record)

    runs = backend.list_recent_runs(limit=3)
    assert len(runs) == 3
    assert runs[0].started_at >= runs[1].started_at >= runs[2].started_at


@mock_aws
def test_get_run_returns_correct_record(settings_override: Settings):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3StateBackend(settings_override)
    record = _make_record("run-findme")
    backend.write_run(record)
    found = backend.get_run("run-findme")
    assert found is not None
    assert found.run_id == "run-findme"


@mock_aws
def test_get_run_not_found_returns_none(settings_override: Settings):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3StateBackend(settings_override)
    assert backend.get_run("does-not-exist") is None


@mock_aws
def test_health_check_true_when_bucket_exists(settings_override: Settings):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    backend = S3StateBackend(settings_override)
    assert backend.health_check() is True
