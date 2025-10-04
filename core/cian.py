from typing import Optional

# Минимальный набор соответствий из спецификации ЦИАН:
# https://www.cian.ru/xml_import/doc/  → в разделах видно строки вида flatSale/flatRent/roomSale/... (Категория)  # noqa

CIAN_CATEGORY = {
    # Квартиры/комнаты
    ("flat",  "sale"): "flatSale",
    ("flat",  "rent"): "flatRent",
    ("room",  "sale"): "roomSale",
    ("room",  "rent"): "roomRent",

    # Загородная — различаем подтип
    ("house", "sale", "house"):     "houseSale",
    ("house", "rent", "house"):     "houseRent",
    ("house", "sale", "cottage"):   "cottageSale",
    ("house", "rent", "cottage"):   "cottageRent",
    ("house", "sale", "townhouse"): "townhouseSale",
    ("house", "rent", "townhouse"): "townhouseRent",
    ("house", "sale", "share"):     "houseShareSale",
    ("house", "rent", "share"):     "houseShareRent",
    # Если поставили подтип "dacha", кладём как дом (IsDacha отдадим отдельным тегом)
    ("house", "sale", "dacha"):     "houseSale",
    ("house", "rent", "dacha"):     "houseRent",

    # Земля
    ("land",  "sale"): "landSale",
    ("land",  "rent"): "landRent",

    # Коммерция — базовые примеры; при нужде расширим
    ("commercial", "sale", "office"):        "officeSale",
    ("commercial", "rent", "office"):        "officeRent",
    ("commercial", "sale", "building"):      "buildingSale",
    ("commercial", "rent", "building"):      "buildingRent",
    ("commercial", "sale", "garage"):        "garageSale",
    ("commercial", "rent", "garage"):        "garageRent",
    ("commercial", "sale", "commercialland"): "commercialLandSale",
    ("commercial", "rent", "commercialland"): "commercialLandRent",
    ("commercial", "sale", "industry"):      "industrySale",
    ("commercial", "rent", "industry"):      "industryRent",
}


def resolve_cian_category(obj) -> Optional[str]:
    """
    Возвращает строку Category по полям:
    - obj.category: flat/room/house/commercial/land
    - obj.operation: sale/rent
    - подтип (если требуется): house_type / commercial_type / land_type
    """

    cat = (getattr(obj, "category", None) or "").strip().lower() or None
    op = (getattr(obj, "operation", None) or "").strip().lower() or None
    if not cat or not op:
        return None

    if cat == "house":
        subtype = (getattr(obj, "house_type", None) or "house").strip().lower()
        return CIAN_CATEGORY.get((cat, op, subtype))
    if cat == "commercial":
        csub = (getattr(obj, "commercial_type", None) or "office").strip().lower()
        return CIAN_CATEGORY.get((cat, op, csub))
    if cat == "land":
        return CIAN_CATEGORY.get((cat, op))
    # flat / room
    return CIAN_CATEGORY.get((cat, op))
