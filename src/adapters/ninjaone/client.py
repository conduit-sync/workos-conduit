# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from src.adapters.ninjaone.refresh_token_store import (
    RefreshTokenRecord,
    RefreshTokenStore,
    SsmRefreshTokenStore,
)

if TYPE_CHECKING:
    from src.config import Settings

log = structlog.get_logger()

_END_USERS_PATH = "/v2/user/end-users"
_END_USER_CREATE_PATH = "/v2/user/end-users"


class NinjaOneAPIError(Exception):
    def __init__(self, status_code: int, response_body: str) -> None:
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"NinjaOne API error {status_code}: {response_body}")


class NinjaOneAuthError(NinjaOneAPIError):
    pass


class NinjaOneRefreshTokenMissing(NinjaOneAuthError):
    def __init__(self) -> None:
        super().__init__(
            401,
            "NinjaOne refresh token is missing. Generate one via the dashboard button "
            "'Generate Refresh Token' or scripts/ninjaone_oauth_bootstrap.py --write-ssm.",
        )


class NinjaOneRefreshTokenExpired(NinjaOneAuthError):
    def __init__(self, response_body: str) -> None:
        super().__init__(
            401,
            "NinjaOne refresh token is expired/invalid. Regenerate via dashboard "
            "'Generate Refresh Token'. Raw error: " + response_body,
        )


class NinjaOneEmailAlreadyInUse(NinjaOneAPIError):
    pass


class NinjaOneAPIClient:
    """HTTP client for NinjaOne using OAuth2 refresh-token flow."""

    def __init__(
        self, settings: Settings, refresh_token_store: RefreshTokenStore | None = None
    ) -> None:
        self._base_url = settings.ninjaone_base_url.rstrip("/")
        self._oauth_client_id = settings.ninjaone_oauth_client_id
        self._oauth_client_secret = settings.ninjaone_oauth_client_secret
        self._oauth_scope = settings.ninjaone_oauth_scope
        self._oauth_token_path = settings.ninjaone_oauth_token_path
        self._refresh_token_lifetime_days = settings.ninjaone_oauth_refresh_token_lifetime_days
        self._timeout = settings.http_timeout_seconds
        self._retry_max = settings.http_retry_max_attempts
        self._backoff_base = settings.http_retry_backoff_base_seconds
        self._refresh_token_store = refresh_token_store or SsmRefreshTokenStore(settings)
        self._access_token: str | None = None
        self._access_token_expiry: float = 0.0

    def invalidate_access_token_cache(self) -> None:
        self._access_token = None
        self._access_token_expiry = 0.0

    def _exchange_refresh_token(self, refresh_token: str) -> tuple[str, int, str | None]:
        url = f"{self._base_url}{self._oauth_token_path}"
        data = {
            "grant_type": "refresh_token",
            "client_id": self._oauth_client_id,
            "client_secret": self._oauth_client_secret,
            "refresh_token": refresh_token,
        }
        headers = {"accept": "application/json"}
        last_exc: Exception | None = None

        for attempt in range(self._retry_max):
            try:
                resp = httpx.post(
                    url,
                    headers=headers,
                    data=data,
                    timeout=self._timeout,
                )
            except httpx.RequestError as exc:
                last_exc = exc
                wait = self._backoff_base * (2**attempt)
                log.warning(
                    "ninjaone_token_network_error",
                    attempt=attempt + 1,
                    retry_in=wait,
                    error=str(exc),
                )
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                last_exc = NinjaOneAPIError(resp.status_code, resp.text)
                wait = self._backoff_base * (2**attempt)
                log.warning(
                    "ninjaone_token_server_error",
                    status_code=resp.status_code,
                    attempt=attempt + 1,
                    retry_in=wait,
                )
                time.sleep(wait)
                continue

            if resp.status_code >= 400:
                if resp.status_code == 400 and "invalid_grant" in resp.text.lower():
                    raise NinjaOneRefreshTokenExpired(resp.text)
                raise NinjaOneAuthError(resp.status_code, resp.text)

            payload = resp.json()
            token = payload.get("access_token")
            expires_in = int(payload.get("expires_in", 3600))
            rotated_refresh = payload.get("refresh_token")
            if not token:
                raise NinjaOneAuthError(resp.status_code, "Missing access_token in response")
            return token, expires_in, rotated_refresh

        raise last_exc or NinjaOneAuthError(0, "Max token retries exceeded")

    def _get_access_token(self) -> str:
        now = time.monotonic()
        if self._access_token and (self._access_token_expiry - now) > 60:
            return self._access_token

        record = self._refresh_token_store.get()
        if not record:
            raise NinjaOneRefreshTokenMissing()

        token, expires_in, rotated_refresh = self._exchange_refresh_token(
            record.refresh_token
        )
        if rotated_refresh and rotated_refresh != record.refresh_token:
            rotated = RefreshTokenRecord.from_refresh_token(
                refresh_token=rotated_refresh,
                scope=record.scope or self._oauth_scope,
                lifetime_days=self._refresh_token_lifetime_days,
                issuer="runtime",
            )
            self._refresh_token_store.put(rotated)

        self._access_token = token
        self._access_token_expiry = time.monotonic() + expires_in
        return token

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        url = f"{self._base_url}{path}"
        unauthorized_retried = False

        while True:
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {self._get_access_token()}",
            }
            last_exc: Exception | None = None

            for attempt in range(self._retry_max):
                try:
                    resp = httpx.request(
                        method,
                        url,
                        headers=headers,
                        timeout=self._timeout,
                        **kwargs,
                    )
                except httpx.RequestError as exc:
                    last_exc = exc
                    wait = self._backoff_base * (2**attempt)
                    log.warning(
                        "ninjaone_request_network_error",
                        method=method,
                        path=path,
                        attempt=attempt + 1,
                        retry_in=wait,
                        error=str(exc),
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code == 401 and not unauthorized_retried:
                    unauthorized_retried = True
                    self.invalidate_access_token_cache()
                    break

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", self._backoff_base))
                    log.warning(
                        "ninjaone_rate_limited",
                        method=method,
                        path=path,
                        attempt=attempt + 1,
                        retry_after=retry_after,
                    )
                    time.sleep(retry_after)
                    continue

                if resp.status_code >= 500:
                    last_exc = NinjaOneAPIError(resp.status_code, resp.text)
                    wait = self._backoff_base * (2**attempt)
                    log.warning(
                        "ninjaone_server_error",
                        method=method,
                        path=path,
                        status_code=resp.status_code,
                        attempt=attempt + 1,
                        retry_in=wait,
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code >= 400:
                    if (
                        resp.status_code == 409
                        and "email_already_in_use" in resp.text.lower()
                    ):
                        raise NinjaOneEmailAlreadyInUse(resp.status_code, resp.text)
                    log.error(
                        "ninjaone_client_error",
                        method=method,
                        path=path,
                        status_code=resp.status_code,
                        body=resp.text[:200],
                    )
                    raise NinjaOneAPIError(resp.status_code, resp.text)

                log.debug(
                    "ninjaone_request_ok",
                    method=method,
                    path=path,
                    status_code=resp.status_code,
                )
                if resp.status_code == 204 or not resp.content:
                    return {}
                return resp.json()
            else:
                log.error(
                    "ninjaone_max_retries_exceeded",
                    method=method,
                    path=path,
                    attempts=self._retry_max,
                    last_error=str(last_exc),
                )
                raise last_exc or NinjaOneAPIError(0, "Max retries exceeded")

            if unauthorized_retried:
                continue

    def get_end_users(self) -> list[dict]:
        result = self._request("GET", _END_USERS_PATH)
        if isinstance(result, list):
            return result
        return result.get("users", result.get("data", []))

    def find_end_user_by_email(self, email: str) -> dict | None:
        for user in self.get_end_users():
            if user.get("email", "").lower() == email.lower():
                return user
        return None

    def create_end_user(self, payload: dict) -> dict:
        return self._request(
            "POST",
            _END_USER_CREATE_PATH,
            json=payload,
            params={"sendInvitation": "false"},
        )

    def update_end_user(self, user_id: int | str, payload: dict) -> dict:
        return self._request("PATCH", f"/v2/user/end-user/{user_id}", json=payload)

    def deactivate_end_user(self, user_id: int | str) -> None:
        self._request("PATCH", f"/v2/user/end-user/{user_id}", json={"enabled": False})

    def health_check(self) -> bool:
        try:
            self._request("GET", _END_USERS_PATH)
            return True
        except Exception:
            return False
