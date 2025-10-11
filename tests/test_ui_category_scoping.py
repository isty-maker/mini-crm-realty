from core.forms import fields_for_category


def _field_set(category: str, operation: str) -> set[str]:
    return set(fields_for_category(category, operation))


def test_flat_sale_has_no_land_house_fields():
    fields = _field_set("flat", "sale")
    assert "land_area" not in fields
    assert "land_area_unit" not in fields
    assert "permitted_land_use" not in fields
    assert "has_electricity" not in fields
    assert "gas_supply_type" not in fields
    assert "water_supply_type" not in fields
    assert "sewerage_type" not in fields
    assert "wc_location" not in fields


def test_house_sale_has_land_engineering_fields():
    fields = _field_set("house", "sale")
    for name in [
        "land_area",
        "land_area_unit",
        "permitted_land_use",
        "has_electricity",
        "gas_supply_type",
        "water_supply_type",
        "sewerage_type",
        "wc_location",
    ]:
        assert name in fields


def test_room_sale_no_flat_or_land_fields():
    fields = _field_set("room", "sale")
    assert "land_area" not in fields
    assert "flat_rooms_count" not in fields


def test_commercial_sale_no_flat_or_land_fields():
    fields = _field_set("commercial", "sale")
    assert "land_area" not in fields
    assert "flat_rooms_count" not in fields
