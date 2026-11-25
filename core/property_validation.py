from django.core.exceptions import ValidationError


NONNEGATIVE_LISTING_FIELDS = {
    "price", "total_area", "living_area", "kitchen_area", "room_area",
    "land_area", "building_ceiling_height", "ceiling_height",
}


def validate_listing_value(name, value):
    if name in NONNEGATIVE_LISTING_FIELDS and value is not None and value < 0:
        raise ValidationError("Значение не может быть отрицательным.")


def required_listing_fields(category, operation):
    """Rules shared by the listing form and its section editors."""
    required = {}
    if category in {"flat", "room", "house"}:
        required["total_area"] = "Укажите общую площадь (TotalArea)."
    if category == "room" and operation == "sale":
        required["rooms_for_sale_count"] = "Для продажи комнаты укажите «Комнат продаётся»."
    return required
