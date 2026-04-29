from __future__ import annotations

import logging

from src.logging_config import configure_logging


def test_configure_stdout(settings_override):
    configure_logging(settings_override)
    root = logging.getLogger()
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)


def test_configure_console_format(settings_override):
    settings_override = settings_override.model_copy(update={"log_format": "console"})
    configure_logging(settings_override)  # must not raise


def test_configure_json_format(settings_override):
    settings_override = settings_override.model_copy(update={"log_format": "json"})
    configure_logging(settings_override)  # must not raise


def test_configure_log_level_debug(settings_override):
    settings_override = settings_override.model_copy(update={"log_level": "DEBUG"})
    configure_logging(settings_override)
    assert logging.getLogger().level == logging.DEBUG


def test_configure_log_level_warning(settings_override):
    settings_override = settings_override.model_copy(update={"log_level": "WARNING"})
    configure_logging(settings_override)
    assert logging.getLogger().level == logging.WARNING


def test_configure_both_output(settings_override, tmp_path):
    log_file = tmp_path / "app.log"
    settings_override = settings_override.model_copy(
        update={"log_output": "both", "log_file_path": str(log_file)}
    )
    configure_logging(settings_override)
    root = logging.getLogger()
    assert len(root.handlers) >= 2


def test_configure_file_output(settings_override, tmp_path):
    log_file = tmp_path / "app.log"
    settings_override = settings_override.model_copy(
        update={"log_output": "file", "log_file_path": str(log_file)}
    )
    configure_logging(settings_override)
    root = logging.getLogger()
    assert any(
        isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
    )


def test_configure_file_output_unwritable_falls_back_to_stdout(settings_override):
    settings_override = settings_override.model_copy(
        update={"log_output": "file", "log_file_path": "/nonexistent/path/app.log"}
    )
    configure_logging(settings_override)  # must not raise; falls back to stdout
    root = logging.getLogger()
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
