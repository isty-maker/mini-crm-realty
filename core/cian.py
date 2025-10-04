from typing import Optional


def _clean(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _house_base(subtype: str) -> str:
    if not subtype:
        return "house"
    if subtype in {"cottage", "kothedge"}:
        return "cottage"
    if subtype in {"townhouse", "таунхаус", "duplex"}:
        return "townhouse"
    if "share" in subtype or "доля" in subtype:
        return "houseShare"
    if subtype in {"dacha", "дача"}:
        return "house"
    return "house"


def _commercial_base(subtype: str) -> str:
    if not subtype:
        return "office"
    mapping = {
        "office": "office",
        "retail": "shoppingArea",
        "shop": "shoppingArea",
        "store": "shoppingArea",
        "warehouse": "warehouse",
        "production": "industry",
        "industry": "industry",
        "free_purpose": "freeAppointmentObject",
        "free_use": "freeAppointmentObject",
        "freepurpose": "freeAppointmentObject",
        "psn": "freeAppointmentObject",
        "building": "building",
        "garage": "garage",
        "commercial_land": "commercialLand",
        "commercialland": "commercialLand",
        "land": "commercialLand",
    }
    for key, value in mapping.items():
        if key in subtype:
            return value
    if "office" in subtype:
        return "office"
    return "office"


def build_cian_category(category: Optional[str], operation: Optional[str], subtype: Optional[str]) -> str:
    cat = _clean(category)
    op = _clean(operation)
    sub = _clean(subtype)

    if not cat or not op:
        return ""

    if cat == "flat":
        if op == "sale":
            return "flatSale"
        if op == "rent_long":
            return "flatRent"
        if op == "rent_daily":
            return "dailyFlatRent"
        return ""

    if cat == "room":
        if op == "sale":
            return "roomSale"
        if op == "rent_long":
            return "roomRent"
        if op == "rent_daily":
            return "dailyRoomRent"
        return ""

    if cat == "house":
        base = _house_base(sub)
        if op == "sale":
            return f"{base}Sale"
        if op == "rent_long":
            return f"{base}Rent"
        if op == "rent_daily":
            return "dailyHouseRent"
        return ""

    if cat == "commercial":
        base = _commercial_base(sub)
        if op == "sale":
            return f"{base}Sale"
        if op == "rent_long":
            return f"{base}Rent"
        if op == "rent_daily":
            return f"{base}Rent"
        return ""

    if cat == "land":
        if op == "sale":
            return "landSale"
        if op == "rent_long":
            return "landRent"
        return ""

    if cat == "garage":
        if op == "sale":
            return "garageSale"
        if op in {"rent_long", "rent_daily"}:
            return "garageRent"
        return ""

    return ""
