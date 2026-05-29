# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from fastapi import Request


def get_session_user(request: Request) -> dict | None:
    return request.session.get("user")


def set_session_user(request: Request, user: dict) -> None:
    request.session["user"] = user


def clear_session(request: Request) -> None:
    request.session.clear()
