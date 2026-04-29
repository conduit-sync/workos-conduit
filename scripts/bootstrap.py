#!/usr/bin/env python3
"""
One-time import of all existing Google Workspace users into the target adapter.
Run BEFORE deploying the ECS task so new events pick up from a clean baseline.

Usage:
    python scripts/bootstrap.py [--dry-run] [--adapter ninjaone]
"""

from __future__ import annotations

import argparse
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


def main() -> None:
    args = parse_args()
    settings = get_settings()
    configure_logging(settings)

    adapter_key = args.adapter or settings.sync_target_adapter

    import workos as workos_sdk

    client = workos_sdk.WorkOSClient(api_key=settings.workos_api_key)
    adapter = get_adapter(adapter_key, settings)

    log.info("bootstrap_started", adapter=adapter_key, dry_run=args.dry_run)

    total = created = skipped = errors = 0
    after = None

    while True:
        kwargs: dict = {"directory": settings.workos_directory_id, "limit": 100}
        if after:
            kwargs["after"] = after

        response = client.directory_sync.list_directory_users(**kwargs)
        users = getattr(response, "data", [])
        if not users:
            break

        for raw_user in users:
            total += 1
            try:
                user = workos_user_to_provisioning(raw_user)
                if args.dry_run:
                    print(f"WOULD CREATE {user.email}")
                    created += 1
                else:
                    result = adapter.provision_user_created(user)
                    action = result.action.value
                    print(f"{action.upper():20s} {user.email}")
                    if action == "created":
                        created += 1
                    elif action == "skipped":
                        skipped += 1
            except Exception as exc:
                errors += 1
                print(
                    f"ERROR               {getattr(raw_user, 'email', '?')}: {exc}",
                    file=sys.stderr,
                )

        # Check for next page
        list_metadata = getattr(response, "list_metadata", None)
        after = getattr(list_metadata, "after", None) if list_metadata else None
        if not after:
            break

    print("\n" + "─" * 50)
    print(f"Total:     {total}")
    print(f"Created:   {created}")
    print(f"Skipped:   {skipped}")
    print(f"Errors:    {errors}")
    if args.dry_run:
        print("\n(Dry run — no changes made)")


if __name__ == "__main__":
    main()
