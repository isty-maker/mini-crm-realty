# core/views.py
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
import os
from functools import lru_cache
from xml.etree.ElementTree import Element, SubElement, tostring
from django.utils.encoding import smart_str
from django.forms.models import model_to_dict

from .models import Property, Photo
from .forms import PropertyForm, PhotoForm, NewObjectStep1Form


def _normalize_category(value):
    if not value:
        return None
    low = value.lower()
    if "flat" in low or "apartment" in low:
        return "flat"
    if "room" in low or "bed" in low:
        return "room"
    if "house" in low or "cottage" in low or "townhouse" in low:
        return "house"
    if "land" in low:
        return "land"
    if (
        "office" in low
        or "industry" in low
        or "warehouse" in low
        or "shopping" in low
        or "commercial" in low
        or "business" in low
        or "building" in low
        or "garage" in low
        or "freeappointment" in low
    ):
        return "commercial"
    return low


def _resolve_operation(prop):
    op = getattr(prop, "operation", None)
    if op:
        return op.lower()
    category = getattr(prop, "category", "") or ""
    low = category.lower()
    if "rent" in low:
        return "rent"
    if "sale" in low:
        return "sale"
    return None


def _has_value(prop, field_name):
    value = getattr(prop, field_name, None)
    if isinstance(value, str):
        return value.strip() != ""
    return value is not None


def _field_verbose_name(field_name):
    try:
        return Property._meta.get_field(field_name).verbose_name
    except FieldDoesNotExist:
        return field_name


def _split_key_value(text):
    if ":" not in text:
        return text.strip(), ""
    key, value = text.split(":", 1)
    value = value.split("#")[0].strip()
    if (value.startswith("\"") and value.endswith("\"")) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    return key.strip(), value


@lru_cache(maxsize=1)
def _load_required_fields():
    required = {"common": [], "deal_terms": [], "by_category": {}}
    path = os.path.join(settings.BASE_DIR, "docs", "cian_fields.yaml")
    if not os.path.exists(path):
        return required

    section = None
    current_category = None
    current_operation = None
    current_model_field = None

    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            indent = len(line) - len(line.lstrip(" "))

            if indent == 0:
                key_part = stripped.split("#", 1)[0].strip()
                if key_part.endswith(":"):
                    key_part = key_part[:-1].strip()
                if key_part in ("common", "deal_terms", "category"):
                    section = key_part
                else:
                    section = None
                current_category = None
                current_operation = None
                current_model_field = None
                continue

            if section == "category":
                if indent == 2:
                    key_part = stripped.split("#", 1)[0].strip()
                    if key_part.endswith(":"):
                        current_category = key_part[:-1].strip()
                        current_operation = None
                        continue
                if indent == 4:
                    key_part = stripped.split("#", 1)[0].strip()
                    if key_part.endswith(":"):
                        current_operation = key_part[:-1].strip()
                        continue
                if indent >= 6:
                    if stripped.startswith("- "):
                        current_model_field = None
                        continue
                    key, value = _split_key_value(stripped)
                    if key == "model_field":
                        current_model_field = value
                    elif (
                        key == "status"
                        and value == "required"
                        and current_model_field
                        and current_category
                        and current_operation
                    ):
                        category_map = required["by_category"].setdefault(
                            current_category, {}
                        )
                        fields = category_map.setdefault(current_operation, [])
                        if current_model_field not in fields:
                            fields.append(current_model_field)
                    continue

            if section in ("common", "deal_terms") and indent >= 2:
                if stripped.startswith("- "):
                    current_model_field = None
                    continue
                key, value = _split_key_value(stripped)
                if key == "model_field":
                    current_model_field = value
                elif key == "status" and value == "required" and current_model_field:
                    fields = required[section]
                    if current_model_field not in fields:
                        fields.append(current_model_field)

    return required


def _collect_missing_fields(prop):
    required = _load_required_fields()
    missing = []

    for field_name in required.get("common", []):
        if not _has_value(prop, field_name):
            missing.append(field_name)

    for field_name in required.get("deal_terms", []):
        if not _has_value(prop, field_name):
            missing.append(field_name)

    category_key = _normalize_category(getattr(prop, "category", None))
    operation_key = _resolve_operation(prop)

    if hasattr(prop, "operation") and not operation_key:
        if "operation" not in missing:
            missing.append("operation")

    if category_key:
        category_map = required.get("by_category", {}).get(category_key, {})
        for field_name in category_map.get(operation_key, []):
            if not _has_value(prop, field_name):
                missing.append(field_name)

    return missing, category_key, operation_key


def _enable_choice_fields(form, field_names):
    for name in field_names:
        field = form.fields.get(name)
        if not field:
            continue
        field.disabled = False
        if "disabled" in field.widget.attrs:
            field.widget.attrs = {
                key: value for key, value in field.widget.attrs.items() if key != "disabled"
            }

def panel_list(request):
    q = request.GET.get("q", "").strip()
    props = Property.objects.all()
    if q:
        props = props.filter(
            Q(title__icontains=q) |
            Q(city__icontains=q) |
            Q(external_id__icontains=q)
        )
    props = props.order_by("-updated_at", "-id")
    return render(request, "core/panel_list.html", {"props": props, "q": q})

def panel_new(request):
    if request.method == "POST":
        form = NewObjectStep1Form(request.POST)
        if form.is_valid():
            create_kwargs = {}
            # category точно сохраняем (поле есть в модели)
            if hasattr(Property, "category"):
                create_kwargs["category"] = form.cleaned_data.get("category") or None
            # operation сохраняем ТОЛЬКО если такое поле существует в модели
            if hasattr(Property, "operation"):
                create_kwargs["operation"] = form.cleaned_data.get("operation") or None

            # title пустой — чтобы форма редактирования не ругалась
            if hasattr(Property, "title"):
                create_kwargs["title"] = ""

            prop = Property.objects.create(**create_kwargs)
            return redirect(f"/panel/edit/{prop.pk}/")
    else:
        form = NewObjectStep1Form()

    return render(request, "core/panel_new_step1.html", {"form": form})

def panel_edit(request, pk):
    """
    Редактирование существующего объекта (без фото-логики).
    """
    prop = get_object_or_404(Property, pk=pk)
    if request.method == "POST":
        form = PropertyForm(request.POST, instance=prop)
        _enable_choice_fields(form, ["category", "operation"])
        if form.is_valid():
            form.save()
            # остаёмся на этой же странице
            return redirect(f"/panel/edit/{prop.pk}/")
    else:
        form = PropertyForm(instance=prop)
        _enable_choice_fields(form, ["category", "operation"])
    # пока без фактических фото — отдадим пустой список для шаблона
    return render(request, "core/panel_edit.html", {"form": form, "prop": prop, "photos": []})

def panel_add_photo(request, pk):
    # TODO: заменить на реальную загрузку (URL или FileField)
    return HttpResponseRedirect(f"/panel/edit/{pk}/")


def panel_delete_photo(request, photo_id):
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/panel/"))


def panel_toggle_main(request, photo_id):
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/panel/"))

# -------- Экспорт ЦИАН (Feed_Version=2) --------
def _add_text(parent, tag, value, always=False):
    if value in (None, "", False) and not always:
        return None
    el = SubElement(parent, tag)
    if value is True: el.text = "true"
    elif value is False: el.text = "false"
    else: el.text = smart_str(value)
    return el

def _add_decimal(parent, tag, value):
    if value is None: return None
    el = SubElement(parent, tag)
    el.text = str(value).replace(",", ".")
    return el

def export_cian(request):
    props = list(Property.objects.all().order_by("id"))
    problems = []

    for prop in props:
        missing, category_key, operation_key = _collect_missing_fields(prop)
        if missing:
            problems.append(
                {
                    "prop": prop,
                    "missing_fields": missing,
                    "missing_verbose": [
                        _field_verbose_name(field_name) for field_name in missing
                    ],
                    "category": category_key,
                    "operation": operation_key,
                }
            )

    if problems:
        return render(
            request,
            "core/export_precheck.html",
            {
                "problems": problems,
            },
        )

    root = Element("Feed")
    SubElement(root, "Feed_Version").text = "2"

    for prop in props:
        obj = SubElement(root, "Object")
        _add_text(obj, "Category", prop.category, always=True)
        _add_text(obj, "ExternalId", prop.external_id, always=True)

        _add_text(obj, "Description", prop.description)
        _add_text(obj, "Address", prop.address)
        if prop.lat is not None and prop.lng is not None:
            coords = SubElement(obj, "Coordinates")
            _add_decimal(coords, "Lat", prop.lat)
            _add_decimal(coords, "Lng", prop.lng)
        _add_text(obj, "CadastralNumber", prop.cadastral_number)

        if prop.phone_number or prop.phone_number2:
            phones = SubElement(obj, "Phones")
            if prop.phone_number:
                ph = SubElement(phones, "PhoneSchema")
                _add_text(ph, "CountryCode", prop.phone_country or "7")
                _add_text(ph, "Number", prop.phone_number)
            if prop.phone_number2:
                ph = SubElement(phones, "PhoneSchema")
                _add_text(ph, "CountryCode", prop.phone_country or "7")
                _add_text(ph, "Number", prop.phone_number2)

        if any([prop.building_name, prop.building_floors, prop.building_build_year,
                prop.building_material, prop.building_ceiling_height,
                prop.building_passenger_lifts, prop.building_cargo_lifts]):
            b = SubElement(obj, "Building")
            _add_text(b, "Name", prop.building_name)
            _add_text(b, "FloorsCount", prop.building_floors)
            _add_text(b, "BuildYear", prop.building_build_year)
            _add_text(b, "MaterialType", prop.building_material)
            _add_decimal(b, "CeilingHeight", prop.building_ceiling_height)
            _add_text(b, "PassengerLiftsCount", prop.building_passenger_lifts)
            _add_text(b, "CargoLiftsCount", prop.building_cargo_lifts)

        if prop.layout_photo_url:
            lp = SubElement(obj, "LayoutPhoto")
            _add_text(lp, "FullUrl", prop.layout_photo_url, always=True)
            _add_text(lp, "IsDefault", True, always=True)
        if prop.object_tour_url:
            t = SubElement(obj, "ObjectTour")
            _add_text(t, "FullUrl", prop.object_tour_url, always=True)

        if prop.photos.exists():
            photos = SubElement(obj, "Photos")
            for p in prop.photos.all():
                ph = SubElement(photos, "PhotoSchema")
                _add_text(ph, "FullUrl", p.full_url, always=True)
                if p.is_default:
                    _add_text(ph, "IsDefault", True, always=True)

        _add_text(obj, "RoomType", prop.room_type)
        _add_text(obj, "FlatRoomsCount", prop.flat_rooms_count)
        _add_text(obj, "IsEuroFlat", prop.is_euro_flat)
        _add_text(obj, "IsApartments", prop.is_apartments)
        _add_text(obj, "IsPenthouse", prop.is_penthouse)

        _add_decimal(obj, "TotalArea", prop.total_area)
        _add_decimal(obj, "LivingArea", prop.living_area)
        _add_decimal(obj, "KitchenArea", prop.kitchen_area)
        _add_text(obj, "FloorNumber", prop.floor_number)
        _add_text(obj, "LoggiasCount", prop.loggias_count)
        _add_text(obj, "BalconiesCount", prop.balconies_count)
        _add_text(obj, "WindowsViewType", prop.windows_view_type)
        _add_text(obj, "SeparateWcsCount", prop.separate_wcs_count)
        _add_text(obj, "CombinedWcsCount", prop.combined_wcs_count)
        _add_text(obj, "RepairType", prop.repair_type)

        if any([prop.jk_id, prop.jk_name, prop.house_id, prop.house_name, prop.flat_number, prop.section_number]):
            jk = SubElement(obj, "JKSchema")
            _add_text(jk, "Id", prop.jk_id)
            _add_text(jk, "Name", prop.jk_name)
            if prop.house_id or prop.house_name:
                house = SubElement(jk, "House")
                _add_text(house, "Id", prop.house_id)
                _add_text(house, "Name", prop.house_name)
            if prop.flat_number or prop.section_number:
                flat = SubElement(jk, "Flat")
                _add_text(flat, "FlatNumber", prop.flat_number)
                _add_text(flat, "SectionNumber", prop.section_number)

        _add_text(obj, "HeatingType", prop.heating_type)
        if any([prop.land_area, prop.land_area_unit, prop.permitted_land_use, prop.is_land_with_contract]):
            land = SubElement(obj, "Land")
            _add_decimal(land, "Area", prop.land_area)
            _add_text(land, "AreaUnitType", prop.land_area_unit)
            _add_text(land, "PermittedLandUseType", prop.permitted_land_use)
            _add_text(land, "IsLandWithContract", prop.is_land_with_contract)
        _add_text(obj, "LandCategory", prop.land_category)
        _add_text(obj, "HasTerrace", prop.has_terrace)
        _add_text(obj, "HasCellar", prop.has_cellar)

        _add_text(obj, "IsRentByParts", prop.is_rent_by_parts)
        _add_text(obj, "RentByPartsDescription", prop.rent_by_parts_desc)
        _add_decimal(obj, "CeilingHeight", prop.ceiling_height)
        _add_text(obj, "ElectricityPower", prop.power)
        _add_text(obj, "HasParking", prop.has_parking)
        _add_text(obj, "ParkingPlaces", prop.parking_places)
        _add_text(obj, "FurnishingDetails", prop.furnishing_details)

        for tag, flag in [
            ("HasInternet", prop.has_internet),
            ("HasFurniture", prop.has_furniture),
            ("HasKitchenFurniture", prop.has_kitchen_furniture),
            ("HasTv", prop.has_tv),
            ("HasWasher", prop.has_washer),
            ("HasConditioner", prop.has_conditioner),
            ("HasRefrigerator", prop.has_refrigerator),
            ("HasDishwasher", prop.has_dishwasher),
            ("HasShower", prop.has_shower),
            ("HasPhone", prop.has_phone),
            ("HasRamp", prop.has_ramp),
            ("HasBathtub", prop.has_bathtub),
        ]:
            _add_text(obj, tag, flag)

        if any([prop.price is not None, prop.mortgage_allowed, prop.agent_bonus_value is not None,
                prop.security_deposit is not None, prop.min_rent_term_months is not None]):
            bt = SubElement(obj, "BargainTerms")
            _add_decimal(bt, "Price", prop.price)
            _add_text(bt, "Currency", prop.currency or "rur")
            _add_text(bt, "MortgageAllowed", prop.mortgage_allowed)
            if prop.agent_bonus_value is not None:
                ab = SubElement(bt, "AgentBonus")
                _add_decimal(ab, "Value", prop.agent_bonus_value)
                _add_text(ab, "PaymentType", "percent" if prop.agent_bonus_is_percent else "fixed")
                if not prop.agent_bonus_is_percent:
                    _add_text(ab, "Currency", prop.currency or "rur")
            _add_decimal(bt, "SecurityDeposit", prop.security_deposit)
            _add_text(bt, "MinRentTerm", prop.min_rent_term_months)

    xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
    return HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")


def panel_generate_feeds(request):
    # получить xml-байты из существующей функции export_cian
    resp = export_cian(request)
    content_type = resp.get("Content-Type", "")
    if not content_type.startswith("application/xml"):
        return resp
    xml_bytes = resp.content

    # гарантировать/media/feeds
    feeds_dir = os.path.join(settings.MEDIA_ROOT, "feeds")
    os.makedirs(feeds_dir, exist_ok=True)

    # записать файл
    out_path = os.path.join(feeds_dir, "cian.xml")
    with open(out_path, "wb") as f:
        f.write(xml_bytes)

    # вернуться на список
    return redirect("/panel/")

