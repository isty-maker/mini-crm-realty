from dataclasses import dataclass
from decimal import Decimal
import json
from urllib.parse import urlsplit

from django import forms
from django.forms.models import fields_for_model
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import Property
from .property_validation import NONNEGATIVE_LISTING_FIELDS, required_listing_fields, validate_listing_value

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
    metrics += {
        "flat": ("living_area", "kitchen_area", "flat_rooms_count", "floor_number"),
        "room": ("room_area", "living_area", "kitchen_area", "rooms_for_sale_count", "floor_number"),
        "house": ("bedrooms_count",),
        "commercial": ("floor_number", "power", "parking_places"),
    }.get(category, ())
    sections = {
        "deal": Section("deal", "Цена и валюта", ("price", "currency")),
        "address": Section("address", "Объект", ("address",)),
        "metrics": Section("metrics", "Характеристики", metrics),
        "description": Section("description", "Описание объявления", ("description",)),
    }
    if category in {"land", "house"}:
        sections["land"] = Section("land", "Участок", ("land_area", "land_area_unit"))
    if category and category != "land":
        building = ("building_floors", "building_build_year", "building_material")
        if category in {"flat", "room"}:
            building += ("building_ceiling_height", "jk_name")
        if category in {"house", "commercial"}:
            building += ("ceiling_height",)
        sections["building"] = Section("building", "Здание", building)
    return {key: section for key, section in sections.items() if section.fields}


def display_fields(prop, section):
    rows = []
    if section.key == "address":
        rows.extend((label, value) for label, value in (
            ("Тип объекта", prop.get_category_display()),
            ("Сделка", prop.get_operation_display()),
        ) if value)
        subtype_fields = {
            "flat": "flat_type", "room": "room_type_ext", "house": "house_type",
            "land": "land_type", "commercial": "commercial_type",
        }
        subtype = subtype_fields.get(prop.category)
        if subtype:
            value = getattr(prop, f"get_{subtype}_display")()
            if value and value != prop.get_category_display():
                rows.append(("Подтип", value))
        return rows
    for name in section.fields:
        if name == "land_area_unit":
            continue
        field = Property._meta.get_field(name)
        value = getattr(prop, name)
        if name == "flat_rooms_count" and value is None:
            value = prop.rooms
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        unit = FIELD_UNITS.get(name, "")
        if name == "land_area":
            unit = prop.get_land_area_unit_display() or ""
        if field.choices:
            value = getattr(prop, f"get_{name}_display")()
        elif isinstance(value, Decimal):
            value = price_display(value)
        rows.append((FIELD_LABELS.get(name, str(field.verbose_name)), f"{value} {unit}".rstrip()))
    return rows


def section_values(prop, section):
    # Category and operation decide which fields and validation rules apply.
    return {name: getattr(prop, name) for name in (*section.fields, "category", "operation")}


def section_version(prop, section):
    version = json.dumps([prop.pk, section.key, section_values(prop, section)], default=str, sort_keys=True)
    return salted_hmac("core.property-section.v1", version, algorithm="sha256").hexdigest()


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
            if isinstance(submitted, str) and isinstance(original, str):
                if submitted.replace("\r\n", "\n") == original.replace("\r\n", "\n"):
                    continue
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


def save_section(prop, section, version, changes):
    """Compare-and-swap the section, preserving fields owned by other editors."""
    if not constant_time_compare(version, section_version(prop, section)):
        return False
    if changes.keys() - set(section.fields):
        raise ValueError("Fields outside the property section")
    if not changes:
        return True
    return Property.objects.filter(pk=prop.pk, **section_values(prop, section)).update(
        **changes, updated_at=timezone.now(),
    ) == 1
