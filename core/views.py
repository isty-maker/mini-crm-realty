# core/views.py
import json
import os
from functools import lru_cache
from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.encoding import smart_str

from .models import Property, Photo
from .cian import build_cian_category
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
    show = request.GET.get("show")
    include_archived = request.GET.get("include_archived") == "1"

    props = Property.objects.all()
    if show == "archived":
        props = props.filter(is_archived=True)
    elif show == "all" or include_archived:
        pass
    else:
        props = props.filter(is_archived=False)

    if q:
        props = props.filter(
            Q(title__icontains=q) |
            Q(city__icontains=q) |
            Q(external_id__icontains=q)
        )
    props = props.order_by("-updated_at", "-id")
    show_archived_flag = include_archived or show == "all"
    return render(
        request,
        "core/panel_list.html",
        {
            "props": props,
            "q": q,
            "show": show,
            "include_archived": show_archived_flag,
        },
    )


def panel_archive(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    prop.status = "archived"
    prop.is_archived = True
    prop.save(update_fields=["status", "is_archived"])
    return redirect("/panel/")


def panel_restore(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    prop.status = "active"
    prop.is_archived = False
    prop.save(update_fields=["status", "is_archived"])
    return redirect("/panel/?show=archived")

def panel_new(request):
    if request.method == "POST":
        form = NewObjectStep1Form(request.POST)
        if form.is_valid():
            cat = form.cleaned_data.get("category","")
            op  = form.cleaned_data.get("operation","")
            return redirect(f"/panel/create/?category={cat}&operation={op}")
    else:
        form = NewObjectStep1Form()
    return render(request, "core/panel_new_step1.html", {"form": form})


def _subtype_choices_payload():
    return json.dumps(PropertyForm.SUBTYPE_CHOICES_MAP, ensure_ascii=False)


def panel_create(request):
    initial = {
        "category": request.GET.get("category", ""),
        "operation": request.GET.get("operation", ""),
    }
    if request.method == "POST":
        form = PropertyForm(request.POST)
        if form.is_valid():
            prop = form.save()
            return redirect(f"/panel/edit/{prop.pk}/")
    else:
        form = PropertyForm(initial=initial)

    return render(
        request,
        "core/panel_edit.html",
        {
            "form": form,
            "prop": None,
            "photos": [],
            "subtype_choices_json": _subtype_choices_payload(),
        },
    )

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
    return render(
        request,
        "core/panel_edit.html",
        {
            "form": form,
            "prop": prop,
            "photos": [],
            "subtype_choices_json": _subtype_choices_payload(),
        },
    )

def panel_add_photo(request, pk):
    # TODO: заменить на реальную загрузку (URL или FileField)
    return HttpResponseRedirect(f"/panel/edit/{pk}/")


def panel_delete_photo(request, photo_id):
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/panel/"))


def panel_toggle_main(request, photo_id):
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/panel/"))

# -------- Экспорт ЦИАН (Feed_Version=2) --------
def _t(parent, tag, value, always=False):
    if value in (None, "", False) and not always:
        return None
    el = SubElement(parent, tag)
    if value is True:
        el.text = "true"
    elif value is False:
        el.text = "false"
    else:
        el.text = smart_str(value)
    return el


def _dec(parent, tag, value):
    if value is None:
        return None
    el = SubElement(parent, tag)
    el.text = str(value).replace(",", ".")
    return el


def _digits_only(s):
    if not s:
        return ""
    return "".join(ch for ch in str(s) if ch.isdigit())


def export_cian(request):
    if request.method not in {"GET", "HEAD"}:
        return HttpResponseNotAllowed(["GET"])

    root = Element("Feed")
    SubElement(root, "Feed_Version").text = "2"  # Спецификация ЦИАН, версия 2  (см. doc)  # noqa

    # В фид попадают только отмеченные для выгрузки
    qs = (
        Property.objects.filter(export_to_cian=True, is_archived=False)
        .order_by("id")
    )

    for prop in qs:
        subtype_value = (
            getattr(prop, "subtype", None)
            or getattr(prop, "house_type", None)
            or getattr(prop, "commercial_type", None)
            or getattr(prop, "land_type", None)
        )
        category_str = build_cian_category(prop.category, prop.operation, subtype_value)
        if not category_str:
            # пропускаем объект без валидной категории
            continue

        obj = SubElement(root, "Object")
        _t(obj, "Category", category_str, always=True)  # например flatSale/houseRent ...
        _t(obj, "ExternalId", getattr(prop, "external_id", "") or "", always=True)

        # Базовые поля
        _t(obj, "Description", getattr(prop, "description", ""))
        _t(obj, "Address", getattr(prop, "address", ""))
        lat = getattr(prop, "lat", None)
        lng = getattr(prop, "lng", None)
        if lat is not None and lng is not None:
            coords = SubElement(obj, "Coordinates")
            _dec(coords, "Lat", lat)
            _dec(coords, "Lng", lng)
        _t(obj, "CadastralNumber", getattr(prop, "cadastral_number", ""))

        # Телефоны (Phones → PhoneSchema → CountryCode/Number)
        phones_added = False
        phones = SubElement(obj, "Phones")
        phone_country = getattr(prop, "phone_country", None) or "7"
        num1 = _digits_only(getattr(prop, "phone_number", ""))
        num2 = _digits_only(getattr(prop, "phone_number2", ""))
        if num1:
            ph = SubElement(phones, "PhoneSchema")
            _t(ph, "CountryCode", phone_country, always=True)
            _t(ph, "Number", num1, always=True)
            phones_added = True
        if num2:
            ph = SubElement(phones, "PhoneSchema")
            _t(ph, "CountryCode", phone_country, always=True)
            _t(ph, "Number", num2, always=True)
            phones_added = True
        if not phones_added:
            obj.remove(phones)  # не шумим пустым контейнером

        # Общие площади
        total_area = getattr(prop, "total_area", None)
        _dec(obj, "TotalArea", total_area)

        # Загородное — домовские поля
        if getattr(prop, "category", "") == "house":
            # Отметка дачи — если подтип dacha
            if getattr(prop, "house_type", "") == "dacha":
                _t(obj, "IsDacha", True, always=True)

            land_area = getattr(prop, "land_area", None)
            land_area_unit = getattr(prop, "land_area_unit", "")
            permitted_land_use = getattr(prop, "permitted_land_use", "")
            is_land_with_contract = getattr(prop, "is_land_with_contract", None)
            land_category = getattr(prop, "land_category", "")
            if any([land_area, land_area_unit, permitted_land_use, is_land_with_contract]):
                land = SubElement(obj, "Land")
                _dec(land, "Area", land_area)
                _t(land, "AreaUnitType", land_area_unit)
                _t(land, "PermittedLandUseType", permitted_land_use)
                if is_land_with_contract is not None:
                    _t(land, "IsLandWithContract", bool(is_land_with_contract), always=True)
            _t(obj, "LandCategory", land_category)
            _t(obj, "HeatingType", getattr(prop, "heating_type", ""))

        # Фото
        photos_qs = getattr(prop, "photos", None)
        if photos_qs and photos_qs.exists():
            photos_el = SubElement(obj, "Photos")
            for p in photos_qs.all():
                ph = SubElement(photos_el, "PhotoSchema")
                _t(ph, "FullUrl", getattr(p, "full_url", ""), always=True)
                if getattr(p, "is_default", False):
                    _t(ph, "IsDefault", True, always=True)

        # Условия сделки (BargainTerms)
        price = getattr(prop, "price", None)
        if (
            price is not None
            or getattr(prop, "mortgage_allowed", None) is not None
            or getattr(prop, "agent_bonus_value", None) is not None
            or getattr(prop, "security_deposit", None) is not None
            or getattr(prop, "min_rent_term_months", None) is not None
        ):
            bt = SubElement(obj, "BargainTerms")
            _dec(bt, "Price", price)
            _t(bt, "Currency", getattr(prop, "currency", None) or "rur")
            if getattr(prop, "mortgage_allowed", None) is not None:
                _t(bt, "MortgageAllowed", bool(getattr(prop, "mortgage_allowed")), always=True)
            # AgentBonus
            abv = getattr(prop, "agent_bonus_value", None)
            if abv is not None:
                ab = SubElement(bt, "AgentBonus")
                _dec(ab, "Value", abv)
                is_percent = bool(getattr(prop, "agent_bonus_is_percent", False))
                _t(ab, "PaymentType", "percent" if is_percent else "fixed", always=True)
                if not is_percent:
                    _t(ab, "Currency", getattr(prop, "currency", None) or "rur")
            # Аренда:
            if getattr(prop, "security_deposit", None) is not None:
                _dec(bt, "SecurityDeposit", getattr(prop, "security_deposit"))
            if getattr(prop, "min_rent_term_months", None) is not None:
                _t(bt, "MinRentTerm", getattr(prop, "min_rent_term_months"))

    xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)

    feeds_dir = os.path.join(settings.MEDIA_ROOT, "feeds")
    os.makedirs(feeds_dir, exist_ok=True)
    out_path = os.path.join(feeds_dir, "cian.xml")
    with open(out_path, "wb") as fh:
        fh.write(xml_bytes)

    response = HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cian.xml"'
    return response


def export_cian_check(request):
    qs = (
        Property.objects.filter(export_to_cian=True, is_archived=False)
        .order_by("id")
    )
    items = []
    for prop in qs:
        category_code = build_cian_category(
            getattr(prop, "category", None),
            getattr(prop, "operation", None),
            getattr(prop, "subtype", None),
        )
        missing = []
        if not category_code:
            missing.append("Category (тип/сделка/подтип)")
        if not (getattr(prop, "external_id", "") or "").strip():
            missing.append("ExternalId")
        if not (getattr(prop, "title", "") or "").strip():
            missing.append("Title")
        category_value = (getattr(prop, "category", "") or "").strip().lower()
        if category_value in {"flat", "room", "house"}:
            if not getattr(prop, "total_area", None):
                missing.append("TotalArea")
        if category_value == "land":
            if not getattr(prop, "land_area", None):
                missing.append("LandArea")
        items.append({
            "prop": prop,
            "category_code": category_code,
            "missing": missing,
        })
    return render(
        request,
        "core/cian_check.html",
        {"items": items},
    )

