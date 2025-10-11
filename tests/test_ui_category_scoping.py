from core.forms import fields_for_category


def _field_set(category: str, operation: str) -> set[str]:
    return set(fields_for_category(category, operation))


def test_house_sale_has_house_utilities():
    house_fields = _field_set("house", "sale")
    for name in ["has_electricity", "has_gas", "has_water", "has_drainage", "power"]:
        assert name in house_fields


def test_flat_sale_no_land_house_fields():
    flat_sale_fields = _field_set("flat", "sale")
    assert "land_area" not in flat_sale_fields
    assert "has_electricity" not in flat_sale_fields
    assert "gas_supply_type" not in flat_sale_fields


def test_flat_rent_has_rent_terms_only():
    flat_rent_fields = _field_set("flat", "rent_long")
    assert "deposit" in flat_rent_fields
    assert "lease_term_type" in flat_rent_fields
    assert "mortgage_allowed" not in flat_rent_fields
