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

        to_delete = []
        for name, field in self.fields.items():
            if name in ("category", "operation"):
                continue
            if isinstance(field, forms.ChoiceField) and has_paren(field.choices):
                to_delete.append(name)
        for name in to_delete:
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

        category = (cleaned_data.get("category") or "").strip()
        operation = (cleaned_data.get("operation") or "").strip()

        if not category:
            self.add_error("category", "Выберите «Тип объекта».")

        if "operation" in self.fields and not operation:
            self.add_error("operation", "Выберите «Тип сделки».")

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
        ("flat","Квартира"), ("room","Комната"),
        ("house","Дом/коттедж"), ("commercial","Коммерческая"), ("land","Земельный участок"),
    ])
    OPERATION_CHOICES = getattr(Property, "OPERATION_CHOICES", [
        ("sale","Продажа"), ("rent","Аренда"),
    ])
    category  = forms.ChoiceField(choices=CATEGORY_CHOICES, label="Тип объекта")
    operation = forms.ChoiceField(choices=OPERATION_CHOICES, label="Тип сделки", required=False)
