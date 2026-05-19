#!/usr/bin/env python3
"""
One-time import of existing WorkOS directory users into the target adapter.

Only users who belong to at least one group in SYNC_ALLOWED_GROUPS are
provisioned.  If SYNC_ALLOWED_GROUPS is empty (allow-all mode) every active
user in the directory is imported.

Run BEFORE deploying the ECS task so new events pick up from a clean baseline.

Usage:
    python scripts/bootstrap.py [--dry-run] [--adapter ninjaone]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from project root without installing
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from src.adapters.base import ProvisioningUser
from src.adapters.registry import get_adapter
from src.config import get_settings
from src.logging_config import configure_logging

log = structlog.get_logger()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap existing users into target adapter"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print actions without executing"
    )
    parser.add_argument("--adapter", default=None, help="Override SYNC_TARGET_ADAPTER")
    return parser.parse_args()


def workos_user_to_provisioning(user) -> ProvisioningUser:
    custom = getattr(user, "custom_attributes", None) or {}
    state = getattr(user, "state", "active")
    return ProvisioningUser(
        email=user.email,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        is_active=(state == "active"),
        department=custom.get("department"),
        job_title=custom.get("job_title"),
        external_id=user.id,
    )


def _next_page_cursor(response) -> str | None:
    meta = getattr(response, "list_metadata", None)
    return getattr(meta, "after", None) if meta else None


def _collect_group_member_ids(client, group) -> set[str]:
    """Return all WorkOS user IDs that are members of a single directory group."""
    member_ids: set[str] = set()
    after = None
    while True:
        kwargs: dict = {"group": group.id, "limit": 100}
        if after:
            kwargs["after"] = after
        resp = client.directory_sync.list_directory_users(**kwargs)
        for u in getattr(resp, "data", []):
            member_ids.add(u.id)
        after = _next_page_cursor(resp)
        if not after:
            break
    return member_ids


def _collect_allowed_user_ids(client, settings) -> set[str] | None:
    """Return WorkOS user IDs that belong to any allowed group.

    Returns None when SYNC_ALLOWED_GROUPS is empty (allow-all mode).
    """
    raw = settings.sync_allowed_groups.strip()
    allowed_groups: list[str] = json.loads(raw) if raw else []
    if not allowed_groups:
        return None

    allowed_set: set[str] = set()
    after = None
    while True:
        kwargs: dict = {"directory": settings.workos_directory_id, "limit": 100}
        if after:
            kwargs["after"] = after
        response = client.directory_sync.list_directory_groups(**kwargs)
        for group in getattr(response, "data", []):
            group_name = getattr(group, "name", "")
            if group_name not in allowed_groups:
                continue
            log.info("bootstrap_scanning_group", group=group_name, group_id=group.id)
            allowed_set |= _collect_group_member_ids(client, group)
        after = _next_page_cursor(response)
        if not after:
            break

    log.info("bootstrap_allowed_users_resolved", count=len(allowed_set))
    return allowed_set


def _provision_user(raw_user, adapter, dry_run: bool) -> tuple[str, None]:
    """Provision a single user; returns (action, None) or raises."""
    user = workos_user_to_provisioning(raw_user)
    if dry_run:
        print(f"WOULD CREATE {user.email}")
        return "created", None
    result = adapter.provision_user_created(user)
    action = result.action.value
    print(f"{action.upper():20s} {user.email}")
    return action, None


def _process_page(users, allowed_user_ids, adapter, dry_run: bool) -> dict:
    counts = {"total": 0, "created": 0, "skipped": 0, "filtered": 0, "errors": 0}
    for raw_user in users:
        counts["total"] += 1
        if allowed_user_ids is not None and raw_user.id not in allowed_user_ids:
            counts["filtered"] += 1
            continue
        try:
            action, _ = _provision_user(raw_user, adapter, dry_run)
            if action in ("created", "skipped"):
                counts[action] += 1
        except Exception as exc:
            counts["errors"] += 1
            print(
                f"ERROR               {getattr(raw_user, 'email', '?')}: {exc}",
                file=sys.stderr,
            )
    return counts


def main() -> None:
    args = parse_args()
    settings = get_settings()
    configure_logging(settings)

    adapter_key = args.adapter or settings.sync_target_adapter

    import workos as workos_sdk

    client = workos_sdk.WorkOSClient(api_key=settings.workos_api_key)
    adapter = get_adapter(adapter_key, settings)

    allowed_user_ids = _collect_allowed_user_ids(client, settings)
    if allowed_user_ids is None:
        log.info("bootstrap_started", adapter=adapter_key, dry_run=args.dry_run, group_filter="all")
    else:
        log.info(
            "bootstrap_started",
            adapter=adapter_key,
            dry_run=args.dry_run,
            group_filter=settings.sync_allowed_groups,
            eligible_users=len(allowed_user_ids),
        )

    totals = {"total": 0, "created": 0, "skipped": 0, "filtered": 0, "errors": 0}
    after = None

    while True:
        kwargs: dict = {"directory": settings.workos_directory_id, "limit": 100}
        if after:
            kwargs["after"] = after
        response = client.directory_sync.list_directory_users(**kwargs)
        users = getattr(response, "data", [])
        if not users:
            break
        page_counts = _process_page(users, allowed_user_ids, adapter, args.dry_run)
        for k, v in page_counts.items():
            totals[k] += v
        after = _next_page_cursor(response)
        if not after:
            break

    print("\n" + "─" * 50)
    print(f"Total scanned: {totals['total']}")
    print(f"Filtered out:  {totals['filtered']}  (not in allowed groups)")
    print(f"Created:       {totals['created']}")
    print(f"Skipped:       {totals['skipped']}  (already existed)")
    print(f"Errors:        {totals['errors']}")
    if args.dry_run:
        print("\n(Dry run — no changes made)")


if __name__ == "__main__":
    main()
