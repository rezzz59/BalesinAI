"""Tests for WhatsApp number normalization."""
import pytest
from fastapi import HTTPException

from app.api.onboard import _validate_wa_number, _normalize_wa
from app.db.tenant_repo import _norm_digits
from app.graph.nodes import _norm_wa


@pytest.mark.parametrize("input_num, expected", [
    ("08123456789", "628123456789"),
    ("628123456789", "628123456789"),
    ("+628123456789", "628123456789"),
    ("8123456789", "628123456789"),
    ("+62 812-3456-789", "628123456789"),
    ("0812 3456 789", "628123456789"),
])
def test_validate_wa_number_valid(input_num, expected):
    assert _validate_wa_number(input_num) == expected


@pytest.mark.parametrize("invalid_num", [
    "",
    "123",  # Too short
    "081234", # Too short
    "0812345678901234567", # Too long (> 16 digits)
    "abcdef", # No digits
])
def test_validate_wa_number_invalid_raises(invalid_num):
    with pytest.raises(HTTPException) as exc:
        _validate_wa_number(invalid_num)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("input_num, expected", [
    ("08123456789", "628123456789"),
    ("628123456789", "628123456789"),
    ("+628123456789", "628123456789"),
    ("8123456789", "628123456789"),
])
def test_normalize_wa(input_num, expected):
    assert _normalize_wa(input_num) == expected


@pytest.mark.parametrize("input_num, expected", [
    ("08123456789", "628123456789"),
    ("628123456789", "628123456789"),
    ("+628123456789", "628123456789"),
    ("123-456@g.us", "123456"), # Groups pass through as digits only (though nodes logic handles this differently)
])
def test_norm_digits_tenant_repo(input_num, expected):
    assert _norm_digits(input_num) == expected


@pytest.mark.parametrize("input_num, expected", [
    ("08123456789", "628123456789"),
    ("628123456789", "628123456789"),
    ("+628123456789", "628123456789"),
    ("1234567890-1234", "12345678901234"), # Group IDs don't get 62 prefixed if they don't start with 0
])
def test_norm_wa_nodes(input_num, expected):
    assert _norm_wa(input_num) == expected