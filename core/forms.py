# core/forms.py
import re

from django import forms
from django.core.exceptions import FieldDoesNotExist

from .models import Property, Photo


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

SUBTYPE_CHOICES_BY_CATEGORY = {
    "house": [
        ("house", "Жилой дом"),
        ("dacha", "Дача"),
        ("townhouse", "Таунхаус"),
        ("duplex", "Дуплекс"),
    ],
    "flat": [
        ("apartment", "Квартира"),
        ("studio", "Студия"),
        ("euro", "Евродвушка/евро-формат"),
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


class PropertyForm(forms.ModelForm):
    SUBTYPE_CHOICES_MAP = SUBTYPE_CHOICES_BY_CATEGORY

    def _resolve_category_for_subtype(self):
        if self.data:
            data_category = self.data.get("category")
            if data_category:
                return data_category.strip().lower()
        initial_category = (self.initial or {}).get("category")
        if initial_category:
            return str(initial_category).strip().lower()
        instance_category = getattr(getattr(self, "instance", None), "category", None)
        if instance_category:
            return str(instance_category).strip().lower()
        return ""

    def _subtype_choices(self, category):
        base = [("", "— не выбрано —")]
        if not category:
            return base
        choices = self.SUBTYPE_CHOICES_MAP.get(category.lower(), [])
        return base + list(choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

        current_category = self._resolve_category_for_subtype()
        existing_subtype_field = self.fields.get("subtype")
        subtype_label = None
        if existing_subtype_field:
            subtype_label = existing_subtype_field.label
        else:
            try:
                subtype_label = (
                    self._meta.model._meta.get_field("subtype").verbose_name.title()
                )
            except FieldDoesNotExist:
                subtype_label = "Подтип объекта"
        self.fields["subtype"] = forms.ChoiceField(
            required=False,
            label=subtype_label,
            choices=self._subtype_choices(current_category),
        )

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

        category = (cleaned_data.get("category") or "").strip().lower()
        operation = (cleaned_data.get("operation") or "").strip()
        subtype = (cleaned_data.get("subtype") or "").strip()

        if not category:
            self.add_error("category", "Выберите «Тип объекта».")

        if "operation" in self.fields and not operation:
            self.add_error("operation", "Выберите «Тип сделки».")

        allowed_subtypes = {
            value for value, _ in self.SUBTYPE_CHOICES_MAP.get(category, [])
        }
        if subtype and subtype not in allowed_subtypes:
            self.add_error(
                "subtype",
                "Выберите подтип из списка, соответствующий выбранной категории.",
            )

        def need(field_name):
            return field_name in self.fields

        if category == "house" and need("house_type") and not cleaned_data.get("house_type"):
            self.add_error(
                "house_type",
                "Выберите подтип дома (дом/дача/коттедж/таунхаус/доля).",
            )

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

        return cleaned_data

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
        }

        widgets = {
            "furnishing_details": forms.TextInput(attrs={"placeholder": "Напр. шкаф, кровать"}),
            "power": forms.NumberInput(attrs={"placeholder": "кВт"}),
            "parking_places": forms.NumberInput(attrs={"placeholder": "Количество мест"}),
            "total_area": forms.NumberInput(attrs={"placeholder": "м²"}),
        }

class PhotoForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ["full_url","is_default"]


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
