# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

if TYPE_CHECKING:
    from src.config import Settings

log = structlog.get_logger()

_USERS_PATH = "/api/v2/users"


class NinjaOneAPIError(Exception):
    def __init__(self, status_code: int, response_body: str) -> None:
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"NinjaOne API error {status_code}: {response_body}")


class NinjaOneAPIClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ninjaone_base_url.rstrip("/")
        self._client_id = settings.ninjaone_client_id
        self._client_secret = settings.ninjaone_client_secret
        self._timeout = settings.http_timeout_seconds
        self._retry_max = settings.http_retry_max_attempts
        self._backoff_base = settings.http_retry_backoff_base_seconds
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._lock = threading.Lock()

    def _get_token(self) -> str:
        with self._lock:
            # Refresh 60 seconds before expiry
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token

            resp = httpx.post(
                f"{self._base_url}/ws/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "monitoring management",
                },
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                raise NinjaOneAPIError(resp.status_code, resp.text)
            data = resp.json()
            self._token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600)
            return self._token

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(self._retry_max):
            token = self._get_token()
            headers = {"Authorization": f"Bearer {token}"}
            try:
                resp = httpx.request(
                    method, url, headers=headers, timeout=self._timeout, **kwargs
                )
            except httpx.RequestError as exc:
                last_exc = exc
                time.sleep(self._backoff_base * (2**attempt))
                continue

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", self._backoff_base))
                time.sleep(retry_after)
                continue

            if resp.status_code >= 500:
                last_exc = NinjaOneAPIError(resp.status_code, resp.text)
                time.sleep(self._backoff_base * (2**attempt))
                continue

            if resp.status_code >= 400:
                raise NinjaOneAPIError(resp.status_code, resp.text)

            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()

        raise last_exc or NinjaOneAPIError(0, "Max retries exceeded")

    def get_technicians(self) -> list[dict]:
        result = self._request("GET", _USERS_PATH, params={"userType": "TECHNICIAN"})
        if isinstance(result, list):
            return result
        return result.get("users", result.get("data", []))

    def find_technician_by_email(self, email: str) -> dict | None:
        technicians = self.get_technicians()
        for tech in technicians:
            if tech.get("email", "").lower() == email.lower():
                return tech
        return None

    def create_technician(self, payload: dict) -> dict:
        return self._request("POST", _USERS_PATH, json=payload)

    def update_technician(self, user_id: int | str, payload: dict) -> dict:
        return self._request("PATCH", f"/api/v2/users/{user_id}", json=payload)

    def deactivate_technician(self, user_id: int | str) -> None:
        self._request("PATCH", f"/api/v2/users/{user_id}", json={"enabled": False})

    def health_check(self) -> bool:
        try:
            self._request(
                "GET", _USERS_PATH, params={"userType": "TECHNICIAN", "limit": 1}
            )
            return True
        except Exception:
            return False
