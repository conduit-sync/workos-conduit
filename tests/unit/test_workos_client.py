from __future__ import annotations

import pytest

from src.workos.client import _DEFAULT_EVENT_TYPES, _parse_event_types


def test_parse_json_array():
    result = _parse_event_types('["dsync.user.created","dsync.user.deleted"]')
    assert result == ["dsync.user.created", "dsync.user.deleted"]


def test_parse_comma_separated():
    raw = "dsync.user.created,dsync.user.updated,dsync.user.deleted"
    result = _parse_event_types(raw)
    assert result == ["dsync.user.created", "dsync.user.updated", "dsync.user.deleted"]


def test_parse_comma_separated_with_spaces():
    raw = " dsync.user.created , dsync.user.updated "
    result = _parse_event_types(raw)
    assert result == ["dsync.user.created", "dsync.user.updated"]


def test_parse_empty_string_returns_defaults():
    assert _parse_event_types("") == _DEFAULT_EVENT_TYPES
    assert _parse_event_types("   ") == _DEFAULT_EVENT_TYPES


def test_parse_invalid_json_raises():
    with pytest.raises(ValueError):
        _parse_event_types("[not valid json")


def test_parse_single_event():
    result = _parse_event_types("dsync.user.created")
    assert result == ["dsync.user.created"]


def test_parse_full_default_comma_separated():
    raw = "dsync.user.created,dsync.user.updated,dsync.user.deleted,dsync.group.user_added,dsync.group.user_removed"
    result = _parse_event_types(raw)
    assert set(result) == set(_DEFAULT_EVENT_TYPES)
