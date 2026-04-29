from __future__ import annotations

import httpx
import pytest
import respx

from src.adapters.ninjaone.client import NinjaOneAPIClient, NinjaOneAPIError


def _make_client(settings_override) -> NinjaOneAPIClient:
    settings_override = settings_override.model_copy(
        update={
            "ninjaone_base_url": "https://ninja.test",
            "http_retry_max_attempts": 2,
            "http_retry_backoff_base_seconds": 0.0,
        }
    )
    return NinjaOneAPIClient(settings_override)


TOKEN_RESP = {"access_token": "tok_abc", "expires_in": 3600}


@respx.mock
def test_get_technicians_returns_list(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.get("https://ninja.test/api/v2/users").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "email": "bob@example.com"}])
    )
    result = client.get_technicians()
    assert result == [{"id": 1, "email": "bob@example.com"}]


@respx.mock
def test_find_technician_by_email_found(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.get("https://ninja.test/api/v2/users").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "email": "Alice@Example.com"},
                {"id": 2, "email": "bob@example.com"},
            ],
        )
    )
    tech = client.find_technician_by_email("alice@example.com")
    assert tech is not None
    assert tech["id"] == 1


@respx.mock
def test_find_technician_by_email_not_found(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.get("https://ninja.test/api/v2/users").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert client.find_technician_by_email("nobody@example.com") is None


@respx.mock
def test_create_technician(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.post("https://ninja.test/api/v2/users").mock(
        return_value=httpx.Response(200, json={"id": 99})
    )
    result = client.create_technician({"email": "new@example.com"})
    assert result["id"] == 99


@respx.mock
def test_update_technician(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.patch("https://ninja.test/api/v2/users/5").mock(
        return_value=httpx.Response(204)
    )
    result = client.update_technician(5, {"firstName": "Bob"})
    assert result == {}


@respx.mock
def test_deactivate_technician(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.patch("https://ninja.test/api/v2/users/3").mock(
        return_value=httpx.Response(204)
    )
    client.deactivate_technician(3)  # must not raise


@respx.mock
def test_request_raises_on_4xx(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.get("https://ninja.test/api/v2/users").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    with pytest.raises(NinjaOneAPIError) as exc_info:
        client.get_technicians()
    assert exc_info.value.status_code == 403


@respx.mock
def test_token_auth_failure_raises(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    with pytest.raises(NinjaOneAPIError) as exc_info:
        client.get_technicians()
    assert exc_info.value.status_code == 401


@respx.mock
def test_health_check_true(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.get("https://ninja.test/api/v2/users").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert client.health_check() is True


@respx.mock
def test_health_check_false_on_error(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.get("https://ninja.test/api/v2/users").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    assert client.health_check() is False


@respx.mock
def test_request_retries_on_5xx_then_fails(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.get("https://ninja.test/api/v2/users").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )
    with pytest.raises(NinjaOneAPIError):
        client.get_technicians()


@respx.mock
def test_get_technicians_wrapped_response(settings_override):
    client = _make_client(settings_override)
    respx.post("https://ninja.test/ws/oauth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESP)
    )
    respx.get("https://ninja.test/api/v2/users").mock(
        return_value=httpx.Response(200, json={"users": [{"id": 5}]})
    )
    result = client.get_technicians()
    assert result == [{"id": 5}]
