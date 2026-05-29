from __future__ import annotations

from fastapi.testclient import TestClient

from src.auth.request_realm import REQUEST_REALM_HEADER
from src.auth.sso import WorkOSSSOService
from src.main import create_app


def _sso_settings(settings_override):
    return settings_override.model_copy(
        update={
            "workos_sso_internal_org_client_id": "client_test",
            "workos_redirect_url_internal": "https://internal.example/auth/callback",
            "workos_redirect_url_eastlake": "https://eastlake.example/auth/callback",
        }
    )


def test_sso_initiate_uses_internal_redirect(settings_override, monkeypatch) -> None:
    settings = _sso_settings(settings_override)
    app = create_app()
    from src import deps
    from src.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_settings] = app.dependency_overrides[get_settings]

    captured: dict[str, str] = {}

    def fake_get_authorization_url(self, state: str, *, redirect_uri: str) -> str:
        captured["redirect_uri"] = redirect_uri
        return "https://workos.example/authorize"

    monkeypatch.setattr(
        WorkOSSSOService,
        "get_authorization_url",
        fake_get_authorization_url,
    )

    client = TestClient(app)
    resp = client.get(
        "/auth/sso/initiate",
        headers={REQUEST_REALM_HEADER: "internal"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert captured["redirect_uri"] == "https://internal.example/auth/callback"


def test_sso_initiate_uses_eastlake_redirect(settings_override, monkeypatch) -> None:
    settings = _sso_settings(settings_override)
    app = create_app()
    from src import deps
    from src.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_settings] = app.dependency_overrides[get_settings]

    captured: dict[str, str] = {}

    def fake_get_authorization_url(self, state: str, *, redirect_uri: str) -> str:
        captured["redirect_uri"] = redirect_uri
        return "https://workos.example/authorize"

    monkeypatch.setattr(
        WorkOSSSOService,
        "get_authorization_url",
        fake_get_authorization_url,
    )

    client = TestClient(app)
    resp = client.get(
        "/auth/sso/initiate",
        headers={REQUEST_REALM_HEADER: "eastlake"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert captured["redirect_uri"] == "https://eastlake.example/auth/callback"


def test_sso_initiate_rejects_unknown_realm(settings_override) -> None:
    settings = _sso_settings(settings_override)
    app = create_app()
    from src import deps
    from src.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_settings] = app.dependency_overrides[get_settings]

    client = TestClient(app)
    resp = client.get(
        "/auth/sso/initiate",
        headers={REQUEST_REALM_HEADER: "west"},
        follow_redirects=False,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not allowed origin"


def test_sso_initiate_rejects_missing_realm_header(settings_override) -> None:
    settings = _sso_settings(settings_override)
    app = create_app()
    from src import deps
    from src.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_settings] = app.dependency_overrides[get_settings]

    client = TestClient(app)
    resp = client.get("/auth/sso/initiate", follow_redirects=False)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not allowed origin"
