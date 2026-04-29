# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from abc import ABC, abstractmethod

from src.adapters.base import BaseTargetAdapter, ProvisioningUser
from src.core.models import HandlerResult


class BaseEventHandler(ABC):
    @abstractmethod
    def can_handle(self, event_type: str) -> bool: ...

    @abstractmethod
    def handle(self, event: dict, adapter: BaseTargetAdapter) -> HandlerResult: ...

    def _workos_event_to_user(self, event_data: dict) -> ProvisioningUser:
        """
        Maps raw WorkOS dsync event data → ProvisioningUser canonical model.
        Extracts email, first_name, last_name, state (→ is_active),
        custom_attributes.department, custom_attributes.job_title, id (→ external_id).
        """
        custom = event_data.get("custom_attributes") or {}
        state = event_data.get("state", "active")
        return ProvisioningUser(
            email=event_data["email"],
            first_name=event_data.get("first_name", ""),
            last_name=event_data.get("last_name", ""),
            is_active=(state == "active"),
            department=custom.get("department"),
            job_title=custom.get("job_title"),
            external_id=event_data["id"],
        )
