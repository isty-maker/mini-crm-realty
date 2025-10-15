# core/forms.py
import re

from django import forms
from django.core.exceptions import FieldDoesNotExist

from .cian import load_registry
from .models import Property, Photo
from .subtypes import CATEGORY_TO_SUBTYPE_FIELD, PROPERTY_SUBTYPE_CHOICES

STATUS_FALLBACK_CHOICES = [
    ("draft", "Черновик"),
    ("active", "Активен"),
    ("archived", "Архив"),
]


def _build_choices(model_attr_name, fallback_values, field_name=None):
    choices = getattr(Property, model_attr_name, None)
    if choices:
        return choices
    if field_name:
        try:
            model_field = Property._meta.get_field(field_name)
            if model_field.choices:
                return model_field.choices
        except FieldDoesNotExist:
            pass
    return [(value, value) for value in fallback_values]


def _split_multi_value(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result = []
        for item in value:
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


FORMS_EXCLUDE = {
    "jk_id",
    "jk_name",
    "house_id",
    "house_name",
    "section_number",
    "undergrounds",
    "metro",
    "object_tour_url",
    "furnishing_details",
}

# Поля, которые мы сознательно не показываем на UI (ЖК/метро/служебные)
UI_EXCLUDE = set(FORMS_EXCLUDE)

# Условия сделки, которые релевантны только для аренды/продажи.
# Используется для UI-фильтрации, чтобы в продаже не появлялись арендные поля
# (и наоборот).
RENT_ONLY_DEAL_TERMS = {
    "deposit",
    "lease_term_type",
    "min_rent_term_months",
    "prepay_months",
    "security_deposit",
    "utilities_terms",
}

SALE_ONLY_DEAL_TERMS = {
    "mortgage_allowed",
    "sale_type",
}


def _required_form_fields_from_registry():
    registry = load_registry()
    fields = set()
    fields |= set(registry.get("common", {}).get("fields", {}).keys())
    fields |= set(registry.get("deal_terms", {}).get("fields", {}).keys())
    categories = registry.get("categories", {}) or {}
    for category in categories.values():
        fields |= set((category.get("fields") or {}).keys())
    # Phones are configured separately in the registry
    fields |= {"phone_country", "phone_number", "phone_number2"}
    return tuple(sorted(field for field in fields if field not in FORMS_EXCLUDE))


def fields_for_category(category: str, operation: str, *, _inherit_from_flat: bool = False):
    """Вернуть отсортированный список имён полей, которые нужно показывать на UI
    для выбранной категории + операции (с учётом исключений)."""

    registry = load_registry()

    fields = set()

    raw_deal_terms = (registry.get("deal_terms", {}) or {}).get("fields", {}) or {}
    if hasattr(raw_deal_terms, "keys"):
        deal_terms_fields = set(raw_deal_terms.keys())
    else:
        deal_terms_fields = set(raw_deal_terms)

    rent_terms = deal_terms_fields & RENT_ONLY_DEAL_TERMS
    sale_terms = deal_terms_fields & SALE_ONLY_DEAL_TERMS
    common_terms = deal_terms_fields - rent_terms - sale_terms

    normalized_category = (category or "").strip()
    normalized_operation = (operation or "").strip()

    category_map = {
        ("flat", "sale"): "flatSale",
        ("flat", "rent"): "flatRent",
        ("room", "sale"): "roomSale",
        ("house", "sale"): "houseSale",
    }

    category_key = None
    if (
        normalized_category == "room"
        and not _inherit_from_flat
    ):
        base_fields = set(
            fields_for_category(
                "flat",
                normalized_operation,
                _inherit_from_flat=True,
            )
        )
        base_fields.discard("flat_rooms_count")
        base_fields.update({"rooms_for_sale_count", "room_area", "room_type_ext"})
        if normalized_operation.startswith("rent"):
            base_fields.update({"room_type", "beds_count"})
        return [name for name in sorted(base_fields) if name not in UI_EXCLUDE]

    if normalized_category == "flat" and normalized_operation.startswith("rent"):
        category_key = "flatRent"
    else:
        category_key = category_map.get((normalized_category, normalized_operation))

    if category_key:
        category_fields = set(
            (registry.get("categories", {}) or {})
            .get(category_key, {})
            .get("fields", {})
            .keys()
        )
        fields |= category_fields
    else:
        category_fields = set()

    if normalized_operation.startswith("rent"):
        fields |= common_terms | rent_terms
    elif normalized_operation == "sale":
        fields |= common_terms | sale_terms
    else:
        fields |= common_terms

    common_all = set((registry.get("common", {}) or {}).get("fields", {}).keys())

    HOUSE_LAND_ONLY = {
        "land_area",
        "land_area_unit",
        "permitted_land_use",
        "is_land_with_contract",
        "land_category",
        "wc_location",
        "has_garage",
        "has_pool",
        "has_bathhouse",
        "has_security",
        "has_terrace",
        "has_cellar",
        "gas_supply_type",
        "water_supply_type",
        "sewerage_type",
        "heating_type",
        "has_drainage",
        "has_water",
        "has_gas",
        "has_electricity",
        "power",
    }
    FLAT_ONLY = {
        "flat_rooms_count",
        "is_apartments",
        "is_penthouse",
        "loggias_count",
        "balconies_count",
        "rooms",
        "windows_view_type",
        "building_passenger_lifts",
        "building_cargo_lifts",
        "building_has_garbage_chute",
    }
    ROOM_ONLY = {"rooms_for_sale_count", "room_type_ext", "room_area"}
    COMMERCIAL_ONLY = {"is_rent_by_parts", "rent_by_parts_desc", "has_ramp", "parking_places"}

    universal = common_all - (HOUSE_LAND_ONLY | FLAT_ONLY | ROOM_ONLY | COMMERCIAL_ONLY)
    fields |= universal

    HOUSE_BASELINE = {"has_electricity", "has_gas", "has_water", "has_drainage", "power"}

    if normalized_category == "flat":
        fields -= HOUSE_LAND_ONLY | ROOM_ONLY | COMMERCIAL_ONLY
    elif normalized_category == "room":
        fields -= HOUSE_LAND_ONLY | FLAT_ONLY | COMMERCIAL_ONLY
    elif normalized_category == "house":
        fields -= FLAT_ONLY | ROOM_ONLY | COMMERCIAL_ONLY
        fields |= HOUSE_BASELINE
    elif normalized_category in {"commercial", "garage", "land"}:
        fields -= FLAT_ONLY | ROOM_ONLY

    fields |= {"phone_country", "phone_number", "phone_number2"}

    return [name for name in sorted(fields) if name not in UI_EXCLUDE]


def group_fields(field_names, category: str = ""):
    """Логически сгруппировать поля (разные наборы для flat/room/house)."""

    cat = (category or "").strip().lower()

    base_groups = [
        ("Основное", ["external_id", "description", "address", "is_rent_by_parts", "rent_by_parts_desc"]),
        ("Гео", ["lat", "lng"]),
    ]

    flat_group = (
        "Площадь и планировка",
        [
            "flat_number",
            "total_area",
            "living_area",
            "kitchen_area",
            "floor_number",
            "rooms",
            "flat_rooms_count",
            "room_type_ext",
            "beds_count",
            "bedrooms_count",
            "loggias_count",
            "balconies_count",
            "windows_view_type",
            "separate_wcs_count",
            "combined_wcs_count",
            "ceiling_height",
            "is_apartments",
            "is_penthouse",
        ],
    )

    room_group = (
        "Комната",
        ["rooms_for_sale_count", "room_area", "room_type", "beds_count"],
    )

    house_area_group = (
        "Дом и участок",
        [
            "house_type",
            "total_area",
            "bedrooms_count",
            "ceiling_height",
            "building_floors",
            "building_build_year",
            "building_material",
            "house_condition",
            "land_area",
            "land_area_unit",
            "permitted_land_use",
            "is_land_with_contract",
            "land_category",
            "wc_location",
            "separate_wcs_count",
            "combined_wcs_count",
        ],
    )

    building_group = (
        "Здание",
        [
            "building_floors",
            "building_build_year",
            "building_material",
            "building_ceiling_height",
            "building_passenger_lifts",
            "building_cargo_lifts",
            "building_series",
            "building_has_garbage_chute",
            "building_parking",
        ],
    )

    engineering_group = (
        "Инженерия (дом/участок)",
        [
            "has_electricity",
            "has_gas",
            "has_water",
            "has_drainage",
            "gas_supply_type",
            "water_supply_type",
            "sewerage_type",
            "heating_type",
            "power",
            "has_parking",
            "parking_places",
            "has_garage",
            "has_pool",
            "has_bathhouse",
            "has_security",
            "has_terrace",
            "has_cellar",
            "has_ramp",
        ],
    )

    amenities_group = (
        "Удобства",
        [
            "is_euro_flat",
            "has_internet",
            "has_furniture",
            "has_kitchen_furniture",
            "has_tv",
            "has_washer",
            "has_conditioner",
            "has_refrigerator",
            "has_dishwasher",
            "has_shower",
            "has_bathtub",
            "has_phone",
            "repair_type",
        ],
    )

    bargain_group = (
        "Условия сделки",
        [
            "price",
            "currency",
            "sale_type",
            "mortgage_allowed",
            "agent_bonus_value",
            "agent_bonus_is_percent",
            "lease_term_type",
            "prepay_months",
            "deposit",
            "security_deposit",
            "client_fee",
            "agent_fee",
            "utilities_terms",
            "bargain_allowed",
            "bargain_price",
            "bargain_conditions",
            "min_rent_term_months",
        ],
    )

    docs_media_contacts = [
        ("Документы", ["cadastral_number"]),
        ("Медиа", ["layout_photo_url"]),
        ("Контакты", ["phone_country", "phone_number", "phone_number2"]),
    ]

    if cat == "house":
        groups_definition = base_groups + [house_area_group, engineering_group, amenities_group, bargain_group] + docs_media_contacts
    elif cat == "room":
        flat_group_for_room = (
            flat_group[0],
            [name for name in flat_group[1] if name not in {"beds_count"}],
        )
        groups_definition = base_groups + [flat_group_for_room, room_group, building_group, amenities_group, bargain_group] + docs_media_contacts
    else:
        groups_definition = base_groups + [flat_group, building_group, amenities_group, bargain_group] + docs_media_contacts

    field_names_list = list(field_names)
    field_names_set = set(field_names_list)

    def only_known(names):
        return [name for name in names if name in field_names_set]

    grouped = []
    used = set()

    for title, names in groups_definition:
        filtered = only_known(names)
        if filtered:
            grouped.append((title, filtered))
            used.update(filtered)

    misc = [name for name in field_names_list if name not in used]

    return grouped, misc


class PropertyForm(forms.ModelForm):
    SUBTYPE_CHOICES_MAP = PROPERTY_SUBTYPE_CHOICES
    SUBTYPE_PLACEHOLDER = "— не выбрано —"
    FEED_RELATED_FIELDS = _required_form_fields_from_registry()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        meta_fields = getattr(self._meta, "fields", None)
        if meta_fields and meta_fields != "__all__":
            if isinstance(meta_fields, str):
                current_fields = [meta_fields]
            else:
                current_fields = list(meta_fields)

            missing_fields = [
                field_name
                for field_name in self.FEED_RELATED_FIELDS
                if field_name not in current_fields
            ]

            if missing_fields:
                current_fields.extend(missing_fields)
                self._meta.fields = tuple(current_fields)

            for field_name in missing_fields:
                if field_name in self.fields:
                    continue
                try:
                    model_field = self._meta.model._meta.get_field(field_name)
                except FieldDoesNotExist:
                    continue
                form_field = model_field.formfield()
                if not form_field:
                    continue
                self.fields[field_name] = form_field
                self.base_fields[field_name] = form_field

        # Убираем легаси-поля с комбинированными категориями (mega-select)
        legacy_category_fields = (
            "category_combined",
            "type_combined",
            "legacy_category",
            "legacy_category_combined",
        )
        for legacy in legacy_category_fields:
            self.fields.pop(legacy, None)

        # Гарантируем, что базовые селекты присутствуют, если есть в модели
        for base in ("category", "operation", "subtype"):
            if hasattr(self._meta.model, base) and base not in self.fields:
                try:
                    model_field = self._meta.model._meta.get_field(base)
                    self.fields[base] = model_field.formfield()
                except Exception:
                    pass

        subtype_label = None
        subtype_help_text = ""
        if "subtype" in self.fields:
            subtype_label = self.fields["subtype"].label
            subtype_help_text = self.fields["subtype"].help_text

        cat_from_data = (self.data.get("category") if self.data else "") or ""
        if not cat_from_data:
            cat_from_data = getattr(self.instance, "category", "") or ""
        if not cat_from_data:
            cat_from_data = self.initial.get("category", "")
        cat_from_data = str(cat_from_data or "").strip()

        subtype_choices = [
            ("", self.SUBTYPE_PLACEHOLDER)
        ] + list(self.SUBTYPE_CHOICES_MAP.get(cat_from_data, []))

        self.fields["subtype"] = forms.ChoiceField(
            choices=subtype_choices,
            required=False,
            label=subtype_label or "Подтип",
            help_text=subtype_help_text,
        )

        if not subtype_label:
            # Если label не удалось получить ранее, используем verbose_name из модели
            try:
                model_field = self._meta.model._meta.get_field("subtype")
                self.fields["subtype"].label = model_field.verbose_name or "Подтип"
            except FieldDoesNotExist:
                pass

        model_defined_choices = list(getattr(self._meta.model, "STATUS_CHOICES", []))
        status_choices = []
        seen_statuses = set()
        for value, label in model_defined_choices + STATUS_FALLBACK_CHOICES:
            if value in seen_statuses:
                continue
            status_choices.append((value, label))
            seen_statuses.add(value)
        status_field = self.fields.get("status")
        status_label = getattr(status_field, "label", None) if status_field else None
        if not status_label:
            try:
                status_label = self._meta.model._meta.get_field("status").verbose_name
            except FieldDoesNotExist:
                status_label = "Статус"
        status_field = forms.ChoiceField(
            choices=status_choices,
            required=False,
            label=status_label or "Статус",
        )
        status_field.empty_value = "draft"
        self.fields["status"] = status_field

        if not self.is_bound:
            explicit_initial = self.initial.get("status")
            if explicit_initial:
                status_field.initial = explicit_initial
            else:
                instance_status = getattr(self.instance, "status", "")
                if getattr(self.instance, "pk", None):
                    status_field.initial = instance_status or status_field.initial
                else:
                    status_field.initial = status_field.initial or "draft"

        def has_paren(choices):
            for choice in choices or []:
                if isinstance(choice, (list, tuple)) and len(choice) == 2:
                    value, label = choice
                    if isinstance(label, (list, tuple)):
                        if has_paren(label):
                            return True
                    else:
                        if "(" in str(value) and ")" in str(value):
                            return True
                        if "(" in str(label) and ")" in str(label):
                            return True
            return False

        for name, field in list(self.fields.items()):
            if name in ("category", "operation", "subtype"):
                continue
            if isinstance(field, forms.ChoiceField) and has_paren(getattr(field, "choices", [])):
                self.fields.pop(name, None)

        self.subtypes_map = self.SUBTYPE_CHOICES_MAP

        def _field_meta(field_name):
            try:
                return self._meta.model._meta.get_field(field_name)
            except FieldDoesNotExist:
                return None

        def _rebuild_single_choice(field_name, choices):
            field = self.fields.get(field_name)
            if not field:
                return
            meta = _field_meta(field_name)
            label = getattr(field, "label", None) or getattr(meta, "verbose_name", None) or field_name
            help_text = getattr(field, "help_text", "") or getattr(meta, "help_text", "")
            attrs = {}
            if getattr(field, "widget", None) is not None:
                attrs.update(getattr(field.widget, "attrs", {}) or {})
            new_field = forms.ChoiceField(
                choices=[("", "— не выбрано —")] + list(choices),
                required=False,
                label=label,
                help_text=help_text,
                widget=forms.Select(attrs=attrs),
            )
            self.fields[field_name] = new_field

        def _rebuild_multi_choice(field_name, choices):
            field = self.fields.get(field_name)
            if not field:
                return
            meta = _field_meta(field_name)
            label = getattr(field, "label", None) or getattr(meta, "verbose_name", None) or field_name
            help_text = getattr(field, "help_text", "") or getattr(meta, "help_text", "")
            attrs = {}
            if getattr(field, "widget", None) is not None:
                attrs.update(getattr(field.widget, "attrs", {}) or {})
            new_field = forms.MultipleChoiceField(
                choices=list(choices),
                required=False,
                label=label,
                help_text=help_text,
                widget=forms.SelectMultiple(attrs=attrs),
            )
            self.fields[field_name] = new_field
            if not self.is_bound:
                existing = self.initial.get(field_name)
                if existing is None:
                    existing = getattr(self.instance, field_name, None)
                initial_list = _split_multi_value(existing)
                if initial_list:
                    new_field.initial = initial_list
                    self.initial[field_name] = initial_list

        normalized_category = (cat_from_data or "").lower()

        if normalized_category == "house":
            _rebuild_single_choice("heating_type", Property.HEATING_TYPE_CHOICES)
            _rebuild_single_choice("house_condition", Property.HOUSE_CONDITION_CHOICES)
            _rebuild_multi_choice("building_material", Property.MATERIAL_TYPE_CHOICES)
        else:
            _rebuild_single_choice("building_material", Property.MATERIAL_TYPE_CHOICES)

    def clean(self):
        cleaned_data = super().clean()

        if "phone_country" in cleaned_data:
            phone_country = (cleaned_data.get("phone_country") or "").strip() or "7"
            cleaned_data["phone_country"] = phone_country

        for field_name in ("phone_number", "phone_number2"):
            raw_value = cleaned_data.get(field_name)
            if raw_value:
                digits_only = re.sub(r"\D+", "", str(raw_value))
                if digits_only.startswith("8") and len(digits_only) == 11:
                    digits_only = digits_only[1:]
                cleaned_data[field_name] = digits_only

        if "category" not in self.fields:
            raise forms.ValidationError(
                "Поле 'category' отсутствует в форме — проверьте шаблон/форму."
            )

        category = (cleaned_data.get("category") or "").strip()
        operation = (cleaned_data.get("operation") or "").strip()

        if not category:
            self.add_error("category", "Выберите «Тип объекта».")

        if "operation" in self.fields and not operation:
            self.add_error("operation", "Выберите «Тип сделки».")

        def need(field_name):
            return field_name in self.fields

        def first_non_empty(*values):
            for value in values:
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    return text
            return ""

        category_key_raw = first_non_empty(
            category,
            (self.initial or {}).get("category"),
            getattr(self.instance, "category", ""),
        )
        category_key = category_key_raw.lower()

        subtype_value = first_non_empty(
            cleaned_data.get("subtype"),
            (self.initial or {}).get("subtype"),
            getattr(self.instance, "subtype", ""),
        )
        allowed_values = {
            value for value, _ in self.SUBTYPE_CHOICES_MAP.get(category_key, [])
        }
        if subtype_value and allowed_values and subtype_value not in allowed_values:
            self.add_error(
                "subtype", "Выберите допустимый подтип для выбранной категории.",
            )

        target_field = CATEGORY_TO_SUBTYPE_FIELD.get(category_key)
        if (
            subtype_value
            and target_field
            and need(target_field)
            and not cleaned_data.get(target_field)
            and (not allowed_values or subtype_value in allowed_values)
        ):
            cleaned_data[target_field] = subtype_value

        if category == "commercial" and need("commercial_type") and not cleaned_data.get("commercial_type"):
            self.add_error(
                "commercial_type",
                "Выберите подтип коммерческой недвижимости.",
            )

        if category == "land" and need("land_type") and not cleaned_data.get("land_type"):
            self.add_error("land_type", "Выберите подтип земельного участка.")

        if category == "flat" and need("flat_type") and not cleaned_data.get("flat_type"):
            self.add_error(
                "flat_type",
                "Выберите подтип квартиры (если применимо).",
            )

        if category == "room" and need("room_type_ext") and not cleaned_data.get("room_type_ext"):
            self.add_error(
                "room_type_ext",
                "Уточните тип комнаты (если применимо).",
            )

        if category in {"flat", "room", "house"} and not cleaned_data.get("total_area"):
            self.add_error("total_area", "Укажите общую площадь (TotalArea).")

        if (
            category == "room"
            and operation == "sale"
            and need("rooms_for_sale_count")
            and not cleaned_data.get("rooms_for_sale_count")
        ):
            self.add_error(
                "rooms_for_sale_count",
                "Для продажи комнаты укажите «Комнат продаётся».",
            )

        status_value = (cleaned_data.get("status") or "").strip()
        if not status_value:
            cleaned_data["status"] = "draft"

        return cleaned_data

    def _post_clean(self):
        status_field = None
        original_choices = None
        appended = False
        try:
            status_field = self._meta.model._meta.get_field("status")
        except FieldDoesNotExist:
            status_field = None

        if status_field is not None:
            original_choices = getattr(status_field, "choices", ())
            existing = {value for value, _ in original_choices}
            if "draft" not in existing:
                appended = True
                status_field.choices = list(original_choices) + [STATUS_FALLBACK_CHOICES[0]]

        try:
            super()._post_clean()
        finally:
            if appended and status_field is not None:
                status_field.choices = original_choices

    class Meta:
        model = Property
        fields = "__all__"
        if any(f.name == "external_id" for f in model._meta.fields):
            exclude = ["external_id"]

        labels = {
            "furnishing_details": "Комплектация",
            "total_area": "Общая площадь, м²",
            "living_area": "Жилая площадь, м²",
            "kitchen_area": "Площадь кухни, м²",
            "rooms": "Количество комнат",
            "floor_number": "Этаж",
            "flat_type": "Подтип квартиры",
            "room_type_ext": "Подтип комнаты",
            "house_type": "Подтип дома",
            "commercial_type": "Подтип коммерции",
            "land_type": "Подтип земельного участка",
            "export_to_domklik": "Экспорт в ДомКлик",
        }

        widgets = {
            "furnishing_details": forms.TextInput(attrs={"placeholder": "Напр. шкаф, кровать"}),
            "power": forms.NumberInput(attrs={"placeholder": "кВт"}),
            "parking_places": forms.NumberInput(attrs={"placeholder": "Количество мест"}),
            "total_area": forms.NumberInput(attrs={"placeholder": "м²"}),
        }

    def clean_building_material(self):
        if "building_material" not in self.fields:
            return self.cleaned_data.get("building_material")
        values = self.cleaned_data.get("building_material")
        codes = _split_multi_value(values)
        if not codes:
            return ""
        allowed = {value for value, _ in Property.MATERIAL_TYPE_CHOICES}
        normalized = []
        for code in codes:
            if code not in allowed:
                raise forms.ValidationError("Выберите допустимые материалы.")
            if code not in normalized:
                normalized.append(code)
        return ",".join(normalized)

class PhotoForm(forms.ModelForm):
    image = forms.FileField(required=False)

    class Meta:
        model = Photo
        fields = ["image", "full_url", "is_default"]

    def clean_full_url(self):
        value = (self.cleaned_data.get("full_url") or "").strip()
        return value


class NewObjectStep1Form(forms.Form):
    CATEGORY_CHOICES = getattr(Property, "CATEGORY_CHOICES", [
        ("house", "Дом"),
        ("flat", "Квартира"),
        ("room", "Комната"),
        ("commercial", "Коммерция"),
        ("land", "Земля"),
        ("garage", "Гараж"),
    ])
    OPERATION_CHOICES = getattr(Property, "OPERATION_CHOICES", [
        ("sale", "Продажа"),
        ("rent_long", "Аренда"),
        ("rent_daily", "Посуточно"),
    ])
    category  = forms.ChoiceField(choices=CATEGORY_CHOICES, label="Тип объекта")
    operation = forms.ChoiceField(choices=OPERATION_CHOICES, label="Тип сделки", required=False)
