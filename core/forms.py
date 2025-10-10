# core/forms.py
import re

from django import forms
from django.core.exceptions import FieldDoesNotExist

from .cian import load_registry
from .models import Property, Photo


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

        subtype_value = (cleaned_data.get("subtype") or "").strip()
        if subtype_value:
            category_key = category or getattr(self.instance, "category", "") or ""
            category_key = str(category_key).strip()
            if not category_key and self.initial:
                category_key = str(self.initial.get("category", "")).strip()
            allowed_values = {
                value for value, _ in self.SUBTYPE_CHOICES_MAP.get(category_key, [])
            }
            if subtype_value not in allowed_values:
                self.add_error("subtype", "Выберите допустимый подтип для выбранной категории.")

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
