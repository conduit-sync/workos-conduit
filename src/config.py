# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # WorkOS
    workos_api_key: str
    workos_directory_id: str
    workos_event_types: str = (
        '["dsync.user.created","dsync.user.updated","dsync.user.deleted",'
        '"dsync.group.user_added","dsync.group.user_removed"]'
    )
    workos_events_page_size: int = 100

    # Adapter selection
    sync_target_adapter: str = "ninjaone"
    sync_stop_on_error: bool = True

    # Backend selection
    cursor_backend: str = "aws"  # "aws" | "local"
    state_backend: str = "aws"  # "aws" | "local"
    local_state_dir: str = (
        ".local-state"  # used when cursor_backend=local or state_backend=local
    )

    # NinjaOne (only required when adapter=ninjaone)
    ninjaone_base_url: str = "https://app.ninjarmm.com"
    ninjaone_oauth_client_id: str = ""
    ninjaone_oauth_client_secret: str = ""
    ninjaone_oauth_scope: str = "control offline_access monitoring management"
    ninjaone_oauth_token_path: str = "/oauth/token"
    ninjaone_oauth_authorize_path: str = "/oauth/authorize"
    ninjaone_oauth_redirect_path: str = "/dashboard/oauth/ninjaone/callback"
    ninjaone_oauth_refresh_token_ssm_param: str = (
        "/workos-conduit/ninjaone/oauth-refresh-token"
    )
    ninjaone_oauth_refresh_token_lifetime_days: int = 30
    # Deprecated compatibility shim for existing .env files.
    ninjaone_api_key: str = ""
    ninjaone_group_role_map: str = '{"organizations_groups_mapping": []}'
    ninjaone_group_role_map_source: str = "env"  # "env" | "ssm"
    ninjaone_group_role_map_ssm_param: str = "/workos-conduit/ninjaone/group-role-map"
    ninjaone_group_admins: str = (
        ""  # WorkOS group name whose members skip create/update
    )

    # HTTP tuning
    http_timeout_seconds: int = 30
    http_retry_max_attempts: int = 3
    http_retry_backoff_base_seconds: float = 1.0

    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""  # only needed for temporary/STS credentials
    aws_profile: str = ""  # optional; selects a named profile from ~/.aws/credentials
    ssm_cursor_param: str = "/workos-conduit/cursor"
    s3_state_bucket: str = ""
    s3_state_prefix: str = "runs/"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    api_secret_key: str = "change-me-in-production"

    # Dashboard
    dashboard_enabled: bool = True
    dashboard_run_history_limit: int = 50
    dashboard_auto_refresh_seconds: int = 60
    dashboard_public_base_url: str = ""

    # Logging
    log_level: str = "INFO"
    log_output: str = "stdout"  # stdout | file | both
    log_format: str = "json"  # json | console
    log_file_path: str = "/var/log/workos-conduit/app.log"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @model_validator(mode="after")
    def validate_config(self) -> Settings:
        if (
            self.ninjaone_group_role_map_source == "ssm"
            and not self.ninjaone_group_role_map_ssm_param
        ):
            raise ValueError(
                "ninjaone_group_role_map_ssm_param required "
                "when ninjaone_group_role_map_source=ssm"
            )
        raw = self.workos_event_types.strip()
        if raw.startswith("["):
            import json as _j

            try:
                _j.loads(raw)
            except Exception as e:
                raise ValueError(f"workos_event_types is not valid JSON: {e}") from e
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
