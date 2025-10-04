# core/forms.py
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
    class Meta:
        model = Property
        fields = [
            "external_id","category",
            "title","description",
            "address","lat","lng","cadastral_number",
            "phone_country","phone_number","phone_number2",
            "layout_photo_url","object_tour_url",

            "building_name","building_floors","building_build_year","building_material",
            "building_ceiling_height","building_passenger_lifts","building_cargo_lifts",

            "room_type","flat_rooms_count","is_euro_flat","is_apartments","is_penthouse",
            "total_area","living_area","kitchen_area","rooms","floor_number",
            "loggias_count","balconies_count","windows_view_type",
            "separate_wcs_count","combined_wcs_count","repair_type",

            "jk_id","jk_name","house_id","house_name","flat_number","section_number",

            "heating_type","land_area","land_area_unit","permitted_land_use","is_land_with_contract","land_category",
            "has_terrace","has_cellar",

            "is_rent_by_parts","rent_by_parts_desc","ceiling_height","power","parking_places","has_parking",

            "furnishing_details","has_internet","has_furniture","has_kitchen_furniture","has_tv","has_washer","has_conditioner",
            "has_refrigerator","has_dishwasher","has_shower","has_phone","has_ramp","has_bathtub",
        
            "price","currency","mortgage_allowed","agent_bonus_value","agent_bonus_is_percent","security_deposit","min_rent_term_months",
        ]

        labels = {
            "furnishing_details": "Комплектация",
            "total_area": "Общая площадь, м²",
            "living_area": "Жилая площадь, м²",
            "kitchen_area": "Площадь кухни, м²",
            "rooms": "Количество комнат",
            "floor_number": "Этаж",
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
    category = forms.ChoiceField(
        choices=_build_choices(
            "CATEGORY_CHOICES",
            ["flat", "house", "room", "land", "commercial"],
            field_name="category",
        )
    )
    operation = forms.ChoiceField(
        choices=_build_choices(
            "OPERATION_CHOICES",
            ["sale", "rent"],
            field_name="operation",
        )
    )
