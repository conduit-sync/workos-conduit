# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024 WorkOS Conduit Contributors

from __future__ import annotations

import logging
import logging.handlers
import sys
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.config import Settings


def configure_logging(settings: Settings) -> None:
    """
    Configure structlog + stdlib logging based on settings.

    log_output=stdout (default): writes to sys.stdout only.
      Ideal for containerised deploys (ECS awslogs driver, Docker, k8s).
    log_output=file: writes to log_file_path only (rotating file handler).
    log_output=both: writes to both.
    log_format=json: renders structured JSON (one event per line).
      Consumed directly by CloudWatch Logs Insights, Datadog, Splunk.
    log_format=console: renders human-readable colourised output for local dev.

    All log records include: timestamp, level, logger, event, plus any
    bound context (run_id, event_id, adapter, etc).
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handlers: list[logging.Handler] = []

    if settings.log_output in ("stdout", "both"):
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        handlers.append(stdout_handler)

    if settings.log_output in ("file", "both"):
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                settings.log_file_path,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
            )
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        except OSError as exc:
            # Fall back to stdout if file path is not writable
            fallback = logging.StreamHandler(sys.stdout)
            fallback.setFormatter(formatter)
            handlers.append(fallback)
            logging.getLogger(__name__).warning(
                "Could not open log file %s: %s — falling back to stdout",
                settings.log_file_path,
                exc,
            )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    for handler in handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Quieten noisy third-party loggers
    for noisy in ("boto3", "botocore", "urllib3", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
