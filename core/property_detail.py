from urllib.parse import urlsplit

from .templatetags.price_display import price_display


def media_url(value):
    """Keep existing HTTP(S) and site-local media links in the detail view."""
    url = (value or "").strip()
    if not url or "\\" in url or any(character.isspace() for character in url):
        return ""
    if url.startswith("/") and not url.startswith("//"):
        return url
    try:
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"} and parsed.hostname and parsed.username is None:
            return url
    except ValueError:
        pass
    return ""


def property_facts(prop):
    facts = []

    def add(label, value, unit=""):
        if isinstance(value, str):
            value = value.strip()
        if value is not None and value != "":
            shown = value if isinstance(value, str) else price_display(value)
            facts.append((label, f"{shown} {unit}".rstrip()))

    add("Тип объекта", prop.get_category_display())
    add("Сделка", prop.get_operation_display())
    subtypes = {
        "flat": prop.get_flat_type_display,
        "room": prop.get_room_type_ext_display,
        "house": prop.get_house_type_display,
        "land": prop.get_land_type_display,
        "commercial": prop.get_commercial_type_display,
    }
    subtype = subtypes.get(prop.category)
    if subtype:
        add("Подтип", subtype())
    if prop.category != "land":
        add("Общая площадь", prop.total_area, "м²")
    if prop.category in {"house", "land"}:
        add("Площадь участка", prop.land_area, prop.get_land_area_unit_display())
    if prop.category in {"flat", "room"}:
        add("Жилая площадь", prop.living_area, "м²")
        add("Кухня", prop.kitchen_area, "м²")
    if prop.category == "flat":
        rooms = prop.flat_rooms_count if prop.flat_rooms_count is not None else prop.rooms
        add("Комнаты", rooms)
    if prop.category == "room":
        add("Комнат продаётся", prop.rooms_for_sale_count)
        add("Площадь комнаты", prop.room_area, "м²")
    if prop.category == "house":
        add("Спальни", prop.bedrooms_count)
    if prop.category in {"flat", "room", "commercial"} and prop.floor_number is not None:
        floor = str(prop.floor_number)
        if prop.building_floors is not None:
            floor += f" из {prop.building_floors}"
        add("Этаж", floor)
    elif prop.category != "land":
        add("Этажей в здании", prop.building_floors)
    if prop.category != "land":
        add("Год постройки", str(prop.building_build_year) if prop.building_build_year is not None else "")
        add("Материал здания", prop.get_building_material_display())
        add("Жилой комплекс", prop.jk_name)
    return facts
