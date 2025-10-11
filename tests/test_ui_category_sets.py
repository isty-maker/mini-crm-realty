from core.forms import fields_for_category, group_fields


def as_set(category: str, operation: str):
    return set(fields_for_category(category, operation))


def test_house_sale_has_utilities_and_land():
    fields = as_set("house", "sale")
    expected = {
        "has_electricity",
        "has_gas",
        "has_water",
        "has_drainage",
        "power",
        "land_area",
        "land_area_unit",
        "permitted_land_use",
    }
    missing = expected - fields
    assert not missing, f"house sale fields missing: {sorted(missing)}"


def test_flat_sale_has_no_house_land_and_no_rent_only():
    fields = as_set("flat", "sale")
    assert "land_area" not in fields
    assert "lease_term_type" not in fields
    assert "deposit" not in fields
    assert "building_passenger_lifts" in fields


def test_room_sale_has_room_specific_but_not_flat_or_land():
    fields = as_set("room", "sale")
    assert "rooms_for_sale_count" in fields
    assert "land_area" not in fields
    assert "flat_rooms_count" not in fields


def test_grouping_house_is_sensible():
    names = sorted(fields_for_category("house", "sale"))
    groups, misc = group_fields(names, "house")
    assert "Дом и участок" in [title for title, _ in groups]
    assert "Инженерия (дом/участок)" in [title for title, _ in groups]
    assert misc == []
