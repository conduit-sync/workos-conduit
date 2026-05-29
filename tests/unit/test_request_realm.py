from __future__ import annotations

import pytest

from src.auth.request_realm import (
    NOT_ALLOWED_ORIGIN,
    RequestRealmError,
    resolve_sso_redirect_uri,
)


def test_resolve_redirect_uri_internal(settings_override) -> None:
    settings = settings_override.model_copy(
        update={
            "workos_redirect_url_internal": "https://internal.example/auth/callback",
            "workos_redirect_url_eastlake": "https://eastlake.example/auth/callback",
        }
    )
    assert (
        resolve_sso_redirect_uri(settings, "internal")
        == "https://internal.example/auth/callback"
    )


def test_resolve_redirect_uri_eastlake(settings_override) -> None:
    settings = settings_override.model_copy(
        update={
            "workos_redirect_url_internal": "https://internal.example/auth/callback",
            "workos_redirect_url_eastlake": "https://eastlake.example/auth/callback",
        }
    )
    assert (
        resolve_sso_redirect_uri(settings, "eastlake")
        == "https://eastlake.example/auth/callback"
    )


def test_resolve_redirect_uri_is_case_insensitive(settings_override) -> None:
    settings = settings_override.model_copy(
        update={"workos_redirect_url_internal": "https://internal.example/auth/callback"}
    )
    assert (
        resolve_sso_redirect_uri(settings, "INTERNAL")
        == "https://internal.example/auth/callback"
    )


@pytest.mark.parametrize("realm", [None, "", "unknown", "west"])
def test_resolve_redirect_uri_rejects_invalid_realm(
    settings_override, realm: str | None
) -> None:
    settings = settings_override.model_copy(
        update={
            "workos_redirect_url_internal": "https://internal.example/auth/callback",
            "workos_redirect_url_eastlake": "https://eastlake.example/auth/callback",
        }
    )
    with pytest.raises(RequestRealmError) as exc_info:
        resolve_sso_redirect_uri(settings, realm)
    assert exc_info.value.message == NOT_ALLOWED_ORIGIN


def test_resolve_redirect_uri_rejects_unconfigured_realm(settings_override) -> None:
    settings = settings_override.model_copy(update={"workos_redirect_url_internal": ""})
    with pytest.raises(RequestRealmError):
        resolve_sso_redirect_uri(settings, "internal")
