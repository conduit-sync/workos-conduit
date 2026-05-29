from __future__ import annotations

import pytest

from src.auth.request_realm import (
    NOT_ALLOWED_ORIGIN,
    WORKOS_SSO_CALLBACK_PATH,
    RequestRealmError,
    build_callback_url,
    resolve_ninjaone_redirect_uri,
    resolve_sso_redirect_uri,
)


def test_resolve_sso_redirect_uri_internal(settings_override) -> None:
    settings = settings_override.model_copy(
        update={
            "dashboard_public_base_url_internal": "https://internal.example",
            "dashboard_public_base_url_eastlake": "https://eastlake.example",
        }
    )
    assert (
        resolve_sso_redirect_uri(settings, "internal")
        == f"https://internal.example{WORKOS_SSO_CALLBACK_PATH}"
    )


def test_resolve_sso_redirect_uri_eastlake(settings_override) -> None:
    settings = settings_override.model_copy(
        update={
            "dashboard_public_base_url_internal": "https://internal.example",
            "dashboard_public_base_url_eastlake": "https://eastlake.example",
        }
    )
    assert (
        resolve_sso_redirect_uri(settings, "eastlake")
        == f"https://eastlake.example{WORKOS_SSO_CALLBACK_PATH}"
    )


def test_resolve_sso_redirect_uri_is_case_insensitive(settings_override) -> None:
    settings = settings_override.model_copy(
        update={"dashboard_public_base_url_internal": "https://internal.example"}
    )
    assert (
        resolve_sso_redirect_uri(settings, "INTERNAL")
        == f"https://internal.example{WORKOS_SSO_CALLBACK_PATH}"
    )


def test_resolve_redirect_uri_uses_default_realm_when_header_missing(
    settings_override,
) -> None:
    settings = settings_override.model_copy(
        update={
            "dashboard_public_base_url_internal": "https://internal.example",
            "request_realm_default": "internal",
        }
    )
    assert (
        resolve_sso_redirect_uri(settings, None)
        == f"https://internal.example{WORKOS_SSO_CALLBACK_PATH}"
    )


def test_resolve_redirect_uri_header_overrides_default_realm(
    settings_override,
) -> None:
    settings = settings_override.model_copy(
        update={
            "dashboard_public_base_url_internal": "https://internal.example",
            "dashboard_public_base_url_eastlake": "https://eastlake.example",
            "request_realm_default": "internal",
        }
    )
    assert (
        resolve_sso_redirect_uri(settings, "eastlake")
        == f"https://eastlake.example{WORKOS_SSO_CALLBACK_PATH}"
    )


@pytest.mark.parametrize("realm", ["unknown", "west"])
def test_resolve_redirect_uri_rejects_invalid_realm(
    settings_override, realm: str
) -> None:
    settings = settings_override.model_copy(
        update={
            "dashboard_public_base_url_internal": "https://internal.example",
            "dashboard_public_base_url_eastlake": "https://eastlake.example",
        }
    )
    with pytest.raises(RequestRealmError) as exc_info:
        resolve_sso_redirect_uri(settings, realm)
    assert exc_info.value.message == NOT_ALLOWED_ORIGIN


@pytest.mark.parametrize("realm", [None, ""])
def test_resolve_redirect_uri_rejects_missing_realm_without_default(
    settings_override, realm: str | None
) -> None:
    settings = settings_override.model_copy(
        update={
            "dashboard_public_base_url_internal": "https://internal.example",
            "dashboard_public_base_url_eastlake": "https://eastlake.example",
            "request_realm_default": "",
        }
    )
    with pytest.raises(RequestRealmError) as exc_info:
        resolve_sso_redirect_uri(settings, realm)
    assert exc_info.value.message == NOT_ALLOWED_ORIGIN


def test_resolve_redirect_uri_rejects_unconfigured_realm(settings_override) -> None:
    settings = settings_override.model_copy(
        update={"dashboard_public_base_url_internal": ""}
    )
    with pytest.raises(RequestRealmError):
        resolve_sso_redirect_uri(settings, "internal")


def test_resolve_ninjaone_redirect_uri_uses_shared_base_and_path(
    settings_override,
) -> None:
    settings = settings_override.model_copy(
        update={
            "dashboard_public_base_url_internal": "https://internal.example",
            "dashboard_public_base_url_eastlake": "https://eastlake.example",
        }
    )
    assert (
        resolve_ninjaone_redirect_uri(settings, "internal")
        == "https://internal.example/dashboard/oauth/ninjaone/callback"
    )
    assert (
        resolve_ninjaone_redirect_uri(settings, "eastlake")
        == "https://eastlake.example/dashboard/oauth/ninjaone/callback"
    )


def test_build_callback_url_strips_trailing_slash_from_base() -> None:
    assert (
        build_callback_url("https://host.example/", "/auth/callback")
        == "https://host.example/auth/callback"
    )
