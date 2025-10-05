from typing import Optional


def _clean(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _is_rent(operation: str) -> bool:
    return operation.startswith("rent")


def build_cian_category(category: Optional[str], operation: Optional[str], subtype: Optional[str]) -> str:
    cat = _clean(category)
    op = _clean(operation)
    sub = _clean(subtype)

    default = "flatSale"
    if not cat:
        return default

    if cat == "flat":
        return "flatRent" if _is_rent(op) else "flatSale"

    if cat == "room":
        return "roomRent" if _is_rent(op) else "roomSale"

    if cat == "house":
        return "houseRent" if _is_rent(op) else "houseSale"

    if cat == "commercial":
        sale_map = {
            "office": "officeSale",
            "retail": "retailSale",
            "warehouse": "warehouseSale",
            "production": "productionSale",
            "free_use": "freeUseSale",
        }
        rent_map = {
            "office": "officeRent",
            "retail": "retailRent",
            "warehouse": "warehouseRent",
            "production": "productionRent",
            "free_use": "freeUseRent",
        }
        if _is_rent(op):
            return rent_map.get(sub, "commercialRent")
        return sale_map.get(sub, "commercialSale")

    if cat == "land":
        if op == "sale":
            return "landSale"
        if _is_rent(op):
            return "landRent"
        return default

    if cat == "garage":
        if op == "sale":
            return "garageSale"
        if _is_rent(op):
            return "garageRent"
        return default

    return default
