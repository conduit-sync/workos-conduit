from __future__ import annotations

import httpx
import pytest
import respx

from src.adapters.ninjaone.client import (
    NinjaOneAPIClient,
    NinjaOneAPIError,
    NinjaOneRefreshTokenExpired,
    NinjaOneRefreshTokenMissing,
)
from src.adapters.ninjaone.refresh_token_store import (
    InMemoryRefreshTokenStore,
    RefreshTokenRecord,
)


def _make_store(token: str = "seed-refresh") -> InMemoryRefreshTokenStore:
    store = InMemoryRefreshTokenStore()
    store.put(
        RefreshTokenRecord.from_refresh_token(
            refresh_token=token,
            scope="control offline_access monitoring management",
            lifetime_days=30,
            issuer="cli",
        )
    )
    return store


def _make_client(
    settings_override, store: InMemoryRefreshTokenStore
) -> NinjaOneAPIClient:
    return NinjaOneAPIClient(
        settings_override.model_copy(
            update={
                "ninjaone_base_url": "https://ninja.test",
                "ninjaone_oauth_client_id": "test-client-id",
                "ninjaone_oauth_client_secret": "test-client-secret",
                "ninjaone_oauth_token_path": "/oauth/token",
                "http_retry_max_attempts": 2,
                "http_retry_backoff_base_seconds": 0.0,
            }
        ),
        refresh_token_store=store,
    )


@respx.mock
def test_get_end_users_returns_list(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "email": "bob@example.com"}])
    )
    result = client.get_end_users()
    assert result == [{"id": 1, "email": "bob@example.com"}]


@respx.mock
def test_bearer_token_sent_on_requests(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    route = respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(200, json=[])
    )
    client.get_end_users()
    assert route.calls[0].request.headers["authorization"] == "Bearer access-1"
    assert "cookie" not in route.calls[0].request.headers


@respx.mock
def test_find_end_user_by_email_found(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "email": "Alice@Example.com"},
                {"id": 2, "email": "bob@example.com"},
            ],
        )
    )
    user = client.find_end_user_by_email("alice@example.com")
    assert user is not None
    assert user["id"] == 1


@respx.mock
def test_find_end_user_by_email_not_found(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert client.find_end_user_by_email("nobody@example.com") is None


@respx.mock
def test_create_end_user(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.post("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(200, json={"id": 99})
    )
    result = client.create_end_user({"email": "new@example.com", "firstName": "New"})
    assert result["id"] == 99


@respx.mock
def test_update_end_user(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.patch("https://ninja.test/v2/user/end-user/5").mock(
        return_value=httpx.Response(204)
    )
    result = client.update_end_user(5, {"firstName": "Bob"})
    assert result == {}


@respx.mock
def test_deactivate_end_user(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.patch("https://ninja.test/v2/user/end-user/3").mock(
        return_value=httpx.Response(204)
    )
    client.deactivate_end_user(3)  # must not raise


@respx.mock
def test_request_raises_on_4xx(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    with pytest.raises(NinjaOneAPIError) as exc_info:
        client.get_end_users()
    assert exc_info.value.status_code == 403


@respx.mock
def test_health_check_true(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert client.health_check() is True


@respx.mock
def test_health_check_false_on_error(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    assert client.health_check() is False


@respx.mock
def test_request_retries_on_5xx_then_fails(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )
    with pytest.raises(NinjaOneAPIError):
        client.get_end_users()


@respx.mock
def test_get_end_users_wrapped_response(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(200, json={"users": [{"id": 5}]})
    )
    result = client.get_end_users()
    assert result == [{"id": 5}]


@respx.mock
def test_access_token_cached_across_calls(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    token_route = respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "access-1", "expires_in": 3600}
        )
    )
    users_route = respx.get("https://ninja.test/v2/user/end-users").mock(
        return_value=httpx.Response(200, json=[])
    )

    client.get_end_users()
    client.get_end_users()

    assert len(token_route.calls) == 1
    assert len(users_route.calls) == 2


@respx.mock
def test_401_triggers_single_refresh_and_retry(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    token_route = respx.post("https://ninja.test/oauth/token").mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "access-1", "expires_in": 3600}),
            httpx.Response(200, json={"access_token": "access-2", "expires_in": 3600}),
        ]
    )
    users_route = respx.get("https://ninja.test/v2/user/end-users").mock(
        side_effect=[
            httpx.Response(401, json={"detail": "expired"}),
            httpx.Response(200, json=[]),
        ]
    )

    client.get_end_users()
    assert len(token_route.calls) == 2
    assert len(users_route.calls) == 2


@respx.mock
def test_invalid_grant_raises_refresh_token_expired(settings_override):
    store = _make_store()
    client = _make_client(settings_override, store)
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "expired refresh token",
            },
        )
    )

    with pytest.raises(NinjaOneRefreshTokenExpired):
        client.get_end_users()


@respx.mock
def test_missing_refresh_token_raises_clear_error(settings_override):
    client = _make_client(settings_override, InMemoryRefreshTokenStore())
    with pytest.raises(NinjaOneRefreshTokenMissing):
        client.get_end_users()
