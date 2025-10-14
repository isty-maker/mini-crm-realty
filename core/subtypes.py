"""Common subtype choice mappings shared across forms and feed serialization."""

PROPERTY_SUBTYPE_CHOICES = {
    "house": [
        ("house", "Жилой дом"),
        ("dacha", "Дача"),
        ("townhouse", "Таунхаус"),
        ("duplex", "Дуплекс"),
    ],
    "flat": [
        ("apartment", "Квартира"),
        ("studio", "Студия"),
        ("euro", "Евро-формат"),
        ("apartments", "Апартаменты"),
    ],
    "room": [
        ("room", "Комната"),
        ("share", "Доля"),
    ],
    "commercial": [
        ("office", "Офис"),
        ("retail", "Торговая"),
        ("warehouse", "Склад"),
        ("production", "Производство"),
        ("free_use", "Свободное назначение"),
    ],
    "land": [
        ("individual_housing", "ИЖС"),
        ("agricultural", "С/Х"),
        ("garden", "Сад/ДНП"),
    ],
    "garage": [
        ("garage", "Гараж"),
        ("parking", "Машиноместо"),
    ],
}

CATEGORY_TO_SUBTYPE_FIELD = {
    "flat": "flat_type",
    "house": "house_type",
    "room": "room_type_ext",
    "commercial": "commercial_type",
    "land": "land_type",
}
