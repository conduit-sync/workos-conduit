from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import respx


def _load_cli_module():
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "ninjaone_oauth_bootstrap.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ninjaone_oauth_bootstrap", script_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@respx.mock
def test_exchange_code_for_token_returns_payload():
    module = _load_cli_module()
    respx.post("https://ninja.test/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
            },
        )
    )
    payload = module.exchange_code_for_token(
        base_url="https://ninja.test",
        token_path="/oauth/token",
        client_id="cid",
        client_secret="sec",
        code="abc",
        redirect_uri="http://localhost:8765/callback",
        timeout_seconds=30,
    )
    assert payload["refresh_token"] == "refresh"
