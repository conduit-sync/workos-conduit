# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from fastapi import APIRouter

from src.api import health, runs, sync

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(sync.router, prefix="/api/v1/sync", tags=["sync"])
api_router.include_router(runs.router, prefix="/api/v1/runs", tags=["runs"])
