#!/usr/bin/env python3
"""
Interactive CLI helper to mint a NinjaOne refresh token and optionally write it to SSM.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.adapters.ninjaone.refresh_token_store import (  # noqa: E402
    RefreshTokenRecord,
    SsmRefreshTokenStore,
)
from src.config import get_settings  # noqa: E402


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    server: "_OAuthCallbackServer"

    def do_GET(self) -> None:  # noqa: N802
        query = parse_qs(urlparse(self.path).query)
        state = query.get("state", [""])[0]
        code = query.get("code", [""])[0]
        error = query.get("error", [""])[0]

        if error:
            self.server.error = error
            self._send(400, f"OAuth failed: {error}")
            self.server.done.set()
            return
        if state != self.server.expected_state:
            self.server.error = "state_mismatch"
            self._send(400, "State mismatch. Close this page and retry.")
            self.server.done.set()
            return
        if not code:
            self.server.error = "missing_code"
            self._send(400, "Missing authorization code.")
            self.server.done.set()
            return

        self.server.code = code
        self._send(200, "Authorization code received. Return to your terminal.")
        self.server.done.set()

    def _send(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):  # type: ignore[override]
        return


class _OAuthCallbackServer(HTTPServer):
    def __init__(self, addr, expected_state: str):
        super().__init__(addr, _OAuthCallbackHandler)
        self.expected_state = expected_state
        self.done = threading.Event()
        self.code: str | None = None
        self.error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate NinjaOne refresh token")
    parser.add_argument("--port", type=int, default=8765, help="Local callback port")
    parser.add_argument(
        "--write-ssm",
        action="store_true",
        help="Write generated refresh token payload into SSM SecureString",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional path to write refresh token payload JSON",
    )
    return parser.parse_args()


def exchange_code_for_token(
    base_url: str,
    token_path: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    timeout_seconds: int,
) -> dict:
    url = f"{base_url.rstrip('/')}{token_path}"
    response = httpx.post(
        url,
        headers={"accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("refresh_token"):
        raise RuntimeError("NinjaOne token response missing refresh_token")
    return payload


def main() -> None:
    args = parse_args()
    settings = get_settings()
    state = secrets.token_hex(32)
    redirect_uri = f"http://localhost:{args.port}/callback"
    authorize_url = (
        f"{settings.ninjaone_base_url.rstrip('/')}{settings.ninjaone_oauth_authorize_path}?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": settings.ninjaone_oauth_client_id,
                "redirect_uri": redirect_uri,
                "scope": settings.ninjaone_oauth_scope,
                "state": state,
            }
        )
    )

    print("Open this URL in your browser to authorize:")
    print(authorize_url)
    print("")

    try:
        webbrowser.open(authorize_url)
    except Exception:
        pass

    server = _OAuthCallbackServer(("127.0.0.1", args.port), expected_state=state)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    print(f"Waiting for OAuth callback on {redirect_uri} ...")
    server.done.wait(timeout=300)
    server.shutdown()
    worker.join(timeout=1)

    if server.error:
        raise RuntimeError(f"OAuth callback failed: {server.error}")
    if not server.code:
        raise RuntimeError("Timed out waiting for OAuth callback")

    token_payload = exchange_code_for_token(
        base_url=settings.ninjaone_base_url,
        token_path=settings.ninjaone_oauth_token_path,
        client_id=settings.ninjaone_oauth_client_id,
        client_secret=settings.ninjaone_oauth_client_secret,
        code=server.code,
        redirect_uri=redirect_uri,
        timeout_seconds=settings.http_timeout_seconds,
    )

    record = RefreshTokenRecord.from_refresh_token(
        refresh_token=token_payload["refresh_token"],
        scope=settings.ninjaone_oauth_scope,
        lifetime_days=settings.ninjaone_oauth_refresh_token_lifetime_days,
        issuer="cli",
    )
    print("Refresh token generated successfully.")
    payload_text = json.dumps(record.model_dump(mode="json"), indent=2)
    print(payload_text)

    if args.output:
        Path(args.output).write_text(payload_text)
        print(f"Wrote payload to {args.output}")

    if args.write_ssm:
        SsmRefreshTokenStore(settings).put(record)
        print(
            "Stored refresh token payload in SSM parameter "
            f"{settings.ninjaone_oauth_refresh_token_ssm_param}"
        )

    now = datetime.now(tz=UTC)
    remaining = record.expires_at - now
    days = remaining.days
    hours = max(int((remaining.seconds % 86400) / 3600), 0)
    print(f"Estimated expiration: {record.expires_at.isoformat()} ({days}d {hours}h)")


if __name__ == "__main__":
    main()
