from __future__ import annotations

from unittest.mock import MagicMock

from src import deps
from src.config import get_settings


def _make_app_with_state(settings_override, state_mock):
    from src.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_state_backend_dep] = lambda: state_mock
    return app


def test_list_runs_empty(settings_override):
    state = MagicMock()
    state.list_recent_runs.return_value = []
    app = _make_app_with_state(settings_override, state)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/api/v1/runs/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_runs_returns_most_recent_first(
    settings_override, sample_run_records, mock_s3
):
    from src.backends.aws.state_s3 import S3StateBackend

    state = S3StateBackend(settings_override)
    app = _make_app_with_state(settings_override, state)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/api/v1/runs/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    # Most recent first
    dates = [d["started_at"] for d in data]
    assert dates == sorted(dates, reverse=True)


def test_list_runs_respects_limit(settings_override, sample_run_records, mock_s3):
    from src.backends.aws.state_s3 import S3StateBackend

    state = S3StateBackend(settings_override)
    app = _make_app_with_state(settings_override, state)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/api/v1/runs/?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_run_found(settings_override, sample_run_records, mock_s3):
    from src.backends.aws.state_s3 import S3StateBackend

    state = S3StateBackend(settings_override)
    app = _make_app_with_state(settings_override, state)
    run_id = sample_run_records[0].run_id

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get(f"/api/v1/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == run_id


def test_get_run_not_found(settings_override, mock_s3):
    from src.backends.aws.state_s3 import S3StateBackend

    state = S3StateBackend(settings_override)
    app = _make_app_with_state(settings_override, state)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/api/v1/runs/nonexistent-run-id")
    assert resp.status_code == 404
