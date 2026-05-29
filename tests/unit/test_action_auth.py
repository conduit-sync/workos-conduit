from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.auth.action_auth import authorize_dashboard_action


def _request_with_session(user: dict | None = None) -> Request:
    scope: dict = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "session": {"user": user} if user is not None else {},
    }
    return Request(scope)


def test_authorize_accepts_valid_api_key(settings_override) -> None:
    settings = settings_override.model_copy(update={"workos_sso_internal_org_client_id": ""})
    request = _request_with_session()
    authorize_dashboard_action(
        request,
        settings,
        settings.api_secret_key,
    )


def test_authorize_accepts_sso_session_when_enabled(settings_override) -> None:
    settings = settings_override.model_copy(update={"workos_sso_internal_org_client_id": "client_test"})
    request = _request_with_session(
        {"id": "user_1", "email": "ops@example.com", "first_name": "Ops", "last_name": "User"}
    )
    authorize_dashboard_action(request, settings, None)


def test_authorize_rejects_missing_credentials(settings_override) -> None:
    settings = settings_override.model_copy(update={"workos_sso_internal_org_client_id": "client_test"})
    request = _request_with_session()
    with pytest.raises(HTTPException) as exc_info:
        authorize_dashboard_action(request, settings, None)
    assert exc_info.value.status_code == 401


def test_authorize_rejects_wrong_api_key(settings_override) -> None:
    settings = settings_override.model_copy(update={"workos_sso_internal_org_client_id": ""})
    request = _request_with_session()
    with pytest.raises(HTTPException) as exc_info:
        authorize_dashboard_action(request, settings, "wrong-key")
    assert exc_info.value.status_code == 401


def test_authorize_sso_session_ignored_when_sso_disabled(settings_override) -> None:
    settings = settings_override.model_copy(update={"workos_sso_internal_org_client_id": ""})
    request = _request_with_session(
        {"id": "user_1", "email": "ops@example.com", "first_name": "Ops", "last_name": "User"}
    )
    with pytest.raises(HTTPException) as exc_info:
        authorize_dashboard_action(request, settings, None)
    assert exc_info.value.status_code == 401
