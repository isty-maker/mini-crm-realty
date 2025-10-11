import pytest

from core.forms import fields_for_category


@pytest.mark.parametrize(
    "category, operation",
    [
        ("house", "sale"),
        ("flat", "sale"),
        ("room", "sale"),
        ("flat", "rent_long"),
        ("flat", "rent_daily"),
    ],
)
def test_fields_are_not_empty(category, operation):
    fields = fields_for_category(category, operation)
    assert fields, f"Expected non-empty field list for {category}/{operation}"


def _collect(category: str, operation: str) -> set[str]:
    return set(fields_for_category(category, operation))


def test_sale_does_not_include_rent_terms():
    fields = _collect("house", "sale")
    assert "lease_term_type" not in fields
    assert "prepay_months" not in fields
    assert "deposit" not in fields
    assert "security_deposit" not in fields
    assert "min_rent_term_months" not in fields


def test_rent_includes_rent_terms():
    fields = _collect("flat", "rent_long")
    assert {"lease_term_type", "prepay_months", "deposit", "security_deposit"}.issubset(fields)


def test_rent_does_not_include_sale_specific_terms():
    fields = _collect("flat", "rent_long")
    assert "sale_type" not in fields
    assert "mortgage_allowed" not in fields


def test_sale_keeps_sale_specific_terms():
    fields = _collect("flat", "sale")
    assert "sale_type" in fields
    assert "mortgage_allowed" in fields
