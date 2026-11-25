from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit

from django import forms
from django.forms.models import fields_for_model

from .models import Property
from .property_validation import NONNEGATIVE_LISTING_FIELDS, required_listing_fields, validate_listing_value

from .property_writes import current_values, property_version, same_form_text, update_property, version_matches
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



@dataclass(frozen=True)
class Section:
    key: str
    title: str
    fields: tuple[str, ...]


FIELD_LABELS = {
    "address": "Адрес",
    "total_area": "Общая площадь",
    "living_area": "Жилая площадь",
    "kitchen_area": "Площадь кухни",
    "room_area": "Площадь комнаты",
    "flat_rooms_count": "Комнаты",
    "rooms_for_sale_count": "Комнат продаётся",
    "bedrooms_count": "Спальни",
    "floor_number": "Этаж",
    "building_floors": "Этажей в здании",
    "building_material": "Материал здания",
    "building_ceiling_height": "Высота потолков",
    "ceiling_height": "Высота потолков",
    "description": "Описание объявления",
}

FIELD_UNITS = {
    "total_area": "м²", "living_area": "м²", "kitchen_area": "м²", "room_area": "м²",
    "building_ceiling_height": "м", "ceiling_height": "м", "power": "кВт",
}


def editable_sections(prop):
    category = prop.category
    metrics = () if category == "land" else ("total_area",)
    residential = ("living_area", "kitchen_area", "floor_number", "room_type",
                   "separate_wcs_count", "combined_wcs_count", "balconies_count", "loggias_count")
    metrics += {
        "flat": (*residential, "flat_rooms_count"),
        "room": (*residential, "room_area", "rooms_for_sale_count"),
        "house": ("bedrooms_count", "house_condition", "heating_type", "wc_location",
                  "sewerage_type", "water_supply_type", "gas_supply_type"),
        "commercial": ("floor_number", "power", "parking_places"),
    }.get(category, ())
    if category and category != "land":
        metrics += ("building_floors", "building_material", "building_build_year")
        if category in {"flat", "room"}:
            metrics += ("building_ceiling_height", "jk_name", "repair_type")
        if category in {"house", "commercial"}:
            metrics += ("ceiling_height", "repair_type")
    sale = ("sale_type",) if prop.operation == "sale" else ()
    terms = ("bargain_allowed", "bargain_conditions", "furnishing_details")
    terms += ("mortgage_allowed",) if prop.operation == "sale" else ()
    sections = {
        "deal": Section("deal", "Цена и валюта", ("price", "currency")),
        "address": Section("address", "Адрес", ("address",)),
        "metrics": Section("metrics", "Характеристики", metrics),
        "terms": Section("terms", "Условия сделки", (*sale, *terms)),
        "description": Section("description", "Описание объявления", ("description",)),
    }
    if category in {"land", "house"}:
        sections["land"] = Section("land", "Участок", ("land_area", "land_area_unit", "permitted_land_use", "land_category"))
    return {key: section for key, section in sections.items() if section.fields}


def property_subtitle(prop):
    category = prop.get_category_display()
    rooms = prop.flat_rooms_count if prop.flat_rooms_count is not None else prop.rooms
    if prop.category == "flat" and rooms is not None and rooms > 0:
        category = f"{rooms}-комнатная квартира"
    return " · ".join(value for value in (category, prop.get_operation_display()) if value)


def display_fields(prop, section, *, staff=False):
    rows = []
    for name in section.fields:
        if name == "furnishing_details" and not staff:
            continue
        if name == "land_area_unit" or (name == "building_floors" and prop.floor_number is not None and "floor_number" in section.fields):
            continue
        field = Property._meta.get_field(name)
        value = getattr(prop, name)
        if name == "flat_rooms_count" and value is None:
            value = prop.rooms
        if name == "floor_number" and value is not None and prop.building_floors is not None:
            value = f"{value}/{prop.building_floors}"
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        unit = FIELD_UNITS.get(name, "")
        if name == "land_area":
            unit = prop.get_land_area_unit_display() or ""
        if field.choices:
            value = getattr(prop, f"get_{name}_display")()
        elif isinstance(value, bool):
            value = "Да" if value else "Нет"
        elif isinstance(value, Decimal):
            value = price_display(value)
        rows.append((FIELD_LABELS.get(name, str(field.verbose_name)), f"{value} {unit}".rstrip()))
    return rows


def section_values(prop, section):
    # Category and operation decide which fields and validation rules apply.
    return current_values(prop, section_scope(section))


def section_scope(section):
    return (*section.fields, "category", "operation")


def section_version(prop, section):
    return property_version(prop, section.key, section_scope(section))


class PropertySectionForm(forms.Form):
    def __init__(self, prop, section, data=None):
        self.prop = prop
        self.section = section
        super().__init__(data, initial=section_values(prop, section), auto_id=f"{section.key}_%s")
        self.fields = fields_for_model(Property, fields=section.fields)
        for name, field in self.fields.items():
            field.label = FIELD_LABELS.get(name, field.label)
            if name in FIELD_UNITS:
                field.label = f"{field.label}, {FIELD_UNITS[name]}"
            if name in NONNEGATIVE_LISTING_FIELDS:
                field.widget.attrs["min"] = 0
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 5
            if name == "flat_rooms_count" and prop.rooms is not None:
                field.help_text = "Отдельное прежнее поле «Количество комнат» доступно в полном редакторе."
            # Old rows can contain choices that the current editor no longer offers.
            if isinstance(field, forms.ChoiceField):
                original = self.initial[name]
                if original not in (None, "") and not field.valid_value(original):
                    field.choices = [*field.choices, (original, original)]

    @property
    def changed_data(self):
        changed = []
        for name in super().changed_data:
            submitted = self.data.get(name)
            original = self.initial[name]
            if not same_form_text(original, submitted):
                changed.append(name)
        return changed

    def clean(self):
        values = super().clean()
        changed = set(self.changed_data)
        required = required_listing_fields(self.prop.category, self.prop.operation)
        for name in changed.intersection(values):
            model_field = Property._meta.get_field(name)
            value = values[name]
            try:
                value = model_field.clean(value, self.prop)
                validate_listing_value(name, value)
                if name in required and not value:
                    raise forms.ValidationError(required[name])
            except forms.ValidationError as error:
                self.add_error(name, error)
            else:
                values[name] = value
        return values

    def changed_values(self):
        return {
            name: self.cleaned_data[name]
            for name in self.changed_data
            if self.cleaned_data[name] != getattr(self.prop, name)
        }


def save_section(prop, section, version, changes, **audit):
    """Compare-and-swap the section, preserving fields owned by other editors."""
    if not version_matches(prop, section.key, section_scope(section), version):
        return False
    if changes.keys() - set(section.fields):
        raise ValueError("Fields outside the property section")
    return update_property(prop, section_scope(section), changes, **audit)
