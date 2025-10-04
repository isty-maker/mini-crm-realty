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

class PropertyForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Гарантируем, что базовые селекты присутствуют, если есть в модели
        for base in ("category", "operation"):
            if hasattr(self._meta.model, base) and base not in self.fields:
                try:
                    model_field = self._meta.model._meta.get_field(base)
                    self.fields[base] = model_field.formfield()
                except Exception:
                    pass

        def has_paren(choices):
            for choice in choices:
                if isinstance(choice, (list, tuple)) and len(choice) == 2:
                    value, label = choice
                    if isinstance(label, (list, tuple)):
                        if has_paren(label):
                            return True
                    else:
                        sval = str(value or "").lower()
                        slab = str(label or "").lower()
                        if "(" in sval and ")" in sval:
                            return True
                        if "(" in slab and ")" in slab:
                            return True
            return False

        for name, field in list(self.fields.items()):
            if isinstance(field, forms.ChoiceField) and has_paren(field.choices):
                self.fields.pop(name, None)

    def clean(self):
        cleaned_data = super().clean()

        phone_country = (cleaned_data.get("phone_country") or "").strip()
        if not phone_country:
            phone_country = "7"
        cleaned_data["phone_country"] = phone_country

        for field_name in ("phone_number", "phone_number2"):
            raw_value = cleaned_data.get(field_name, "") or ""
            digits_only = re.sub(r"\D+", "", str(raw_value))
            if digits_only.startswith("8") and len(digits_only) == 11:
                digits_only = digits_only[1:]
            cleaned_data[field_name] = digits_only

        category = cleaned_data.get("category")
        if not category:
            self.add_error("category", "Выберите категорию объекта.")

        if "operation" in self.fields:
            operation = cleaned_data.get("operation")
            if not operation:
                self.add_error("operation", "Выберите тип сделки.")

        category_value = (category or "").lower()
        housing_keywords = (
            "flat",
            "room",
            "house",
            "cottage",
            "townhouse",
            "bed",
        )
        needs_total_area = any(keyword in category_value for keyword in housing_keywords)

        total_area = cleaned_data.get("total_area")
        if needs_total_area and not total_area:
            self.add_error(
                "total_area",
                "Для объектов жилья укажите общую площадь.",
            )

        return cleaned_data

    class Meta:
        model = Property
        fields = "__all__"
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
        ("flat","Квартира"), ("room","Комната"),
        ("house","Дом/коттедж"), ("commercial","Коммерческая"), ("land","Земельный участок"),
    ])
    OPERATION_CHOICES = getattr(Property, "OPERATION_CHOICES", [
        ("sale","Продажа"), ("rent","Аренда"),
    ])
    category  = forms.ChoiceField(choices=CATEGORY_CHOICES, label="Тип объекта")
    operation = forms.ChoiceField(choices=OPERATION_CHOICES, label="Тип сделки", required=False)
