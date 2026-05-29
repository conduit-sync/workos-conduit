from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient
from moto import mock_aws

from src.auth.request_realm import REQUEST_REALM_HEADER
from src.main import create_app

_PUBLIC_BASE = "http://localhost:8080"
_REALM_HEADERS = {REQUEST_REALM_HEADER: "internal"}


def _realm_settings(settings_override):
    return settings_override.model_copy(
        update={
            "dashboard_public_base_url_internal": _PUBLIC_BASE,
            "dashboard_public_base_url_eastlake": "http://eastlake.localhost:8080",
        }
    )


@mock_aws
def test_oauth_start_with_sso_session(settings_override, monkeypatch):
    from src.auth.sso import WorkOSSSOService

    settings = settings_override.model_copy(
        update={
            "workos_sso_internal_org_client_id": "client_test",
            "dashboard_public_base_url_internal": "http://testserver",
        }
    )
    app = create_app()
    app.dependency_overrides = {}
    from src import deps
    from src.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_settings] = app.dependency_overrides[get_settings]

    fixed_state = "a" * 64
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

    client = TestClient(app)
    client.get(
        "/auth/sso/initiate",
        headers=_REALM_HEADERS,
        follow_redirects=False,
    )
    client.get(
        f"/auth/callback?code=test-code&state={fixed_state}",
        follow_redirects=False,
    )

    resp = client.post(
        "/dashboard/oauth/ninjaone/start",
        headers=_REALM_HEADERS,
    )
    assert resp.status_code == 200
    assert "/oauth/authorize" in resp.json()["authorize_url"]


@mock_aws
def test_oauth_start_requires_api_key(settings_override):
    app = create_app()
    app.dependency_overrides = {}
    from src import deps
    from src.config import get_settings

    app.dependency_overrides[get_settings] = lambda: _realm_settings(settings_override)
    app.dependency_overrides[deps.get_settings] = app.dependency_overrides[get_settings]
    client = TestClient(app)

    resp = client.post("/dashboard/oauth/ninjaone/start", headers=_REALM_HEADERS)
    assert resp.status_code == 401


@mock_aws
def test_oauth_start_returns_authorize_url(settings_override):
    app = create_app()
    app.dependency_overrides = {}
    from src import deps
    from src.config import get_settings

    app.dependency_overrides[get_settings] = lambda: _realm_settings(settings_override)
    app.dependency_overrides[deps.get_settings] = app.dependency_overrides[get_settings]
    client = TestClient(app)

    resp = client.post(
        "/dashboard/oauth/ninjaone/start",
        headers={
            "X-API-Key": settings_override.api_secret_key,
            **_REALM_HEADERS,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "/oauth/authorize" in data["authorize_url"]
    assert "state=" in data["authorize_url"]
    assert "redirect_uri=" in data["authorize_url"]
    assert "localhost%3A8080" in data["authorize_url"]


@mock_aws
def test_oauth_start_rejects_missing_realm(settings_override):
    app = create_app()
    from src import deps
    from src.config import get_settings

    settings = _realm_settings(settings_override).model_copy(
        update={"request_realm_default": ""}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_settings] = app.dependency_overrides[get_settings]
    client = TestClient(app)

    resp = client.post(
        "/dashboard/oauth/ninjaone/start",
        headers={"X-API-Key": settings.api_secret_key},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not allowed origin"


@mock_aws
@respx.mock
def test_oauth_callback_exchanges_code_and_writes_ssm(settings_override):
    app = create_app()
    app.dependency_overrides = {}
    from src import deps
    from src.config import get_settings

    settings = _realm_settings(settings_override)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_settings] = app.dependency_overrides[get_settings]
    client = TestClient(app)

    start = client.post(
        "/dashboard/oauth/ninjaone/start",
        headers={"X-API-Key": settings.api_secret_key, **_REALM_HEADERS},
    )
    authorize_url = start.json()["authorize_url"]
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(authorize_url).query)["state"][0]

    respx.post(
        f"{settings.ninjaone_base_url}{settings.ninjaone_oauth_token_path}"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "acc",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            },
        )
    )
    resp = client.get(
        f"/dashboard/oauth/ninjaone/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "oauth_status=success" in resp.headers["location"]
