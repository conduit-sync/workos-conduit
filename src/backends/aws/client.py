from __future__ import annotations

from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from src.config import Settings


def make_boto_client(service: str, settings: Settings) -> boto3.client:
    """Return a boto3 client, passing explicit credentials when set in config."""
    kwargs: dict = {"region_name": settings.aws_region}
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
    if settings.aws_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    if settings.aws_session_token:
        kwargs["aws_session_token"] = settings.aws_session_token
    if settings.aws_profile:
        session = boto3.Session(profile_name=settings.aws_profile)
        return session.client(service, **kwargs)
    return boto3.client(service, **kwargs)
