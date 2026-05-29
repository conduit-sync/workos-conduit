# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_CLIENT_ID_RE = re.compile(r"^\d+$")


def validate_portal_email(email: str) -> str:
    normalized = email.strip()
    if not normalized or not _EMAIL_RE.match(normalized):
        raise ValueError("A valid email address is required")
    return normalized


def validate_portal_client_id(client_id: str) -> str:
    normalized = client_id.strip()
    if not normalized or not _CLIENT_ID_RE.match(normalized):
        raise ValueError("Client ID must contain numbers only")
    return normalized
