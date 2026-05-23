from __future__ import annotations

from unittest.mock import MagicMock

from src import deps


def test_liveness(test_client):
    resp = test_client.get("/health/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_liveness_without_trailing_slash(test_client):
    resp = test_client.get("/health", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_all_healthy(test_client, settings_override):
    mock_adapter = MagicMock()
    mock_adapter.adapter_key = "ninjaone"
    mock_adapter.health_check.return_value = True

    mock_cursor = MagicMock()
    mock_cursor.health_check.return_value = True

    mock_state = MagicMock()
    mock_state.health_check.return_value = True

    from src.config import get_settings
    from src.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_adapter_dep] = lambda: mock_adapter
    app.dependency_overrides[deps.get_cursor_backend_dep] = lambda: mock_cursor
    app.dependency_overrides[deps.get_state_backend_dep] = lambda: mock_state

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_readiness_adapter_unhealthy(test_client, settings_override):
    mock_adapter = MagicMock()
    mock_adapter.adapter_key = "ninjaone"
    mock_adapter.health_check.return_value = False

    mock_cursor = MagicMock()
    mock_cursor.health_check.return_value = True

    mock_state = MagicMock()
    mock_state.health_check.return_value = True

    from src.config import get_settings
    from src.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_settings] = lambda: settings_override
    app.dependency_overrides[deps.get_adapter_dep] = lambda: mock_adapter
    app.dependency_overrides[deps.get_cursor_backend_dep] = lambda: mock_cursor
    app.dependency_overrides[deps.get_state_backend_dep] = lambda: mock_state

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/health/ready")
    assert resp.status_code == 503
