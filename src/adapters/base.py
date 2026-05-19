# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from src.core.models import HandlerResult


class ProvisioningUser(BaseModel):
    """
    Canonical, adapter-agnostic user model.
    WorkOS events are always mapped to this before reaching any adapter.
    """

    email: str
    first_name: str
    last_name: str
    is_active: bool
    department: str | None = None
    job_title: str | None = None
    external_id: str  # WorkOS directory_user ID


class ProvisioningGroup(BaseModel):
    """Canonical group membership event."""

    user: ProvisioningUser
    group_name: str
    action: str  # "added" | "removed"


class BaseTargetAdapter(ABC):
    """
    Abstract base class for all provisioning targets.

    To add a new target (e.g. Zendesk):
      1. Create src/adapters/zendesk/adapter.py
      2. Implement ZendeskAdapter(BaseTargetAdapter)
      3. Register in src/adapters/registry.py with register_adapter("zendesk", ...)
      No other files need to change.
    """

    @property
    @abstractmethod
    def adapter_key(self) -> str:
        """Unique identifier string e.g. 'ninjaone', 'zendesk'."""

    @abstractmethod
    def provision_user_created(self, user: ProvisioningUser) -> HandlerResult:
        """Idempotent: if user already exists, return action=SKIPPED."""

    @abstractmethod
    def provision_user_updated(self, user: ProvisioningUser) -> HandlerResult:
        """If not found fall through to created. If no diff return NO_CHANGE."""

    @abstractmethod
    def provision_user_deactivated(self, user: ProvisioningUser) -> HandlerResult:
        """Never hard-delete. If already inactive return ALREADY_INACTIVE."""

    @abstractmethod
    def provision_group_membership(self, group: ProvisioningGroup) -> HandlerResult:
        """Map group name to role. Return SKIPPED if no mapping exists."""

    @abstractmethod
    def watched_groups(self) -> set[str]:
        """Return group names this adapter is configured to process.

        Used by the engine to filter user events — only users in these groups
        are provisioned. Return an empty set to allow all users through.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if target system is reachable. Used by /health/ready."""
