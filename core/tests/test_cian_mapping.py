from core.cian import build_cian_category


def test_category_flat_sale_rent():
    assert build_cian_category("flat", "sale", None) == "flatSale"
    assert build_cian_category("flat", "rent_long", None) == "flatRent"


def test_category_room_sale_rent():
    assert build_cian_category("room", "sale", None) == "roomSale"
    assert build_cian_category("room", "rent_daily", None) == "roomRent"


def test_category_house_sale_rent():
    assert build_cian_category("house", "sale", None) == "houseSale"
    assert build_cian_category("house", "rent_long", None) == "houseRent"


def test_category_land_sale_default():
    assert build_cian_category("land", "sale", None) == "landSale"


def test_category_commercial_free_purpose():
    assert (
        build_cian_category("commercial", "sale", "free_purpose") == "freeUseSale"
    )
    assert (
        build_cian_category("commercial", "rent_long", "free_purpose")
        == "freeUseRent"
    )
