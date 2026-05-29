from __future__ import annotations

import pytest

from src.workos.portal_validation import validate_portal_client_id, validate_portal_email


def test_validate_portal_email_accepts_valid() -> None:
    assert validate_portal_email("  user@example.com  ") == "user@example.com"


@pytest.mark.parametrize("email", ["", "not-an-email", "a@", "@b.com"])
def test_validate_portal_email_rejects_invalid(email: str) -> None:
    with pytest.raises(ValueError, match="valid email"):
        validate_portal_email(email)


def test_validate_portal_client_id_accepts_digits() -> None:
    assert validate_portal_client_id(" 12345 ") == "12345"


@pytest.mark.parametrize("client_id", ["", "abc", "12a34", "12.34"])
def test_validate_portal_client_id_rejects_non_numeric(client_id: str) -> None:
    with pytest.raises(ValueError, match="numbers only"):
        validate_portal_client_id(client_id)
