from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from src import deps
from src.config import get_settings
from src.core.models import RunRecord, RunStatus
from src.core.sync_engine import SyncEngine


def _make_run_record() -> RunRecord:
    now = datetime(2024, 4, 1, 12, 0, 0, tzinfo=UTC)
    return RunRecord(
        run_id="run-test-001",
        adapter="ninjaone",
        started_at=now,
        finished_at=now,
        duration_seconds=0.5,
        status=RunStatus.SUCCESS,
        trigger_source="api",
        events_fetched=2,
        events_processed=2,
        cursor_before=None,
        cursor_after="evt_last",
        results=[],
        errors=[],
    )


def _make_app(settings_override, engine_mock):
    from src.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_sync_engine] = lambda: engine_mock
    return app


def test_trigger_sync_success(settings_override):
    engine = MagicMock(spec=SyncEngine)
    engine.run_cycle.return_value = _make_run_record()
    app = _make_app(settings_override, engine)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/sync/trigger",
            json={"trigger_source": "api"},
            headers={"X-API-Key": "test-secret-key"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "run-test-001"
    assert data["status"] == "success"


def test_trigger_sync_wrong_api_key(settings_override):
    engine = MagicMock(spec=SyncEngine)
    app = _make_app(settings_override, engine)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/sync/trigger",
            json={},
            headers={"X-API-Key": "wrong-key"},
        )
    assert resp.status_code == 401


def test_trigger_sync_with_sso_session(settings_override, monkeypatch):
    from src.auth.request_realm import REQUEST_REALM_HEADER
    from src.auth.sso import WorkOSSSOService

    settings = settings_override.model_copy(
        update={
            "workos_sso_internal_org_client_id": "client_test",
            "workos_redirect_url_internal": "http://testserver/auth/callback",
        }
    )
    engine = MagicMock(spec=SyncEngine)
    engine.run_cycle.return_value = _make_run_record()
    app = _make_app(settings, engine)

    fixed_state = "b" * 64
    monkeypatch.setattr(
        "src.dashboard.login_router.secrets.token_hex",
        lambda _n: fixed_state,
    )
    monkeypatch.setattr(
        WorkOSSSOService,
        "exchange_code",
        lambda self, code: {
            "id": "user_1",
            "email": "ops@example.com",
            "first_name": "Ops",
            "last_name": "User",
        },
    )

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        client.get(
            "/auth/sso/initiate",
            headers={REQUEST_REALM_HEADER: "internal"},
            follow_redirects=False,
        )
        client.get(
            f"/auth/callback?code=test-code&state={fixed_state}",
            follow_redirects=False,
        )
        resp = client.post(
            "/api/v1/sync/trigger",
            json={"trigger_source": "dashboard"},
        )
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run-test-001"


def test_trigger_sync_missing_api_key(settings_override):
    engine = MagicMock(spec=SyncEngine)
    app = _make_app(settings_override, engine)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.post("/api/v1/sync/trigger", json={})
    assert resp.status_code in (401, 422)


def test_trigger_sync_dashboard_source(settings_override):
    engine = MagicMock(spec=SyncEngine)
    record = _make_run_record()
    record = record.model_copy(update={"trigger_source": "dashboard"})
    engine.run_cycle.return_value = record
    app = _make_app(settings_override, engine)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/sync/trigger",
            json={"trigger_source": "dashboard"},
            headers={"X-API-Key": "test-secret-key"},
        )
    assert resp.status_code == 200
    engine.run_cycle.assert_called_once_with(trigger_source="dashboard")


def test_sync_status_empty(settings_override):
    mock_state = MagicMock()
    mock_state.list_recent_runs.return_value = []

    from src.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_state_backend_dep] = lambda: mock_state

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/api/v1/sync/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "no_runs"
