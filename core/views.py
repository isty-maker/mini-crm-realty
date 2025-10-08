import json
import logging
import os
import re
from functools import lru_cache
from io import BytesIO
from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import FieldDoesNotExist
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models import Max, Q
from django.http import (
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils.encoding import smart_str

try:
    from PIL import Image, ImageFile, UnidentifiedImageError
except (ImportError, AttributeError):  # pragma: no cover - support for trimmed Pillow stub
    from PIL import Image  # type: ignore

    class _StubImageFile:  # pragma: no cover - minimal stub
        LOAD_TRUNCATED_IMAGES = False

    ImageFile = _StubImageFile  # type: ignore

    class UnidentifiedImageError(Exception):
        pass

from .cian import build_cian_category
from .forms import PropertyForm
from .models import Photo, Property


ImageFile.LOAD_TRUNCATED_IMAGES = True

log = logging.getLogger("upload")


def _encode_jpeg_to_target(img, base_name, orig_bytes):
    target = max(150 * 1024, len(orig_bytes) // 5)  # ~×5
    lo, hi = 65, 90
    best = None
    while lo <= hi:
        q = (lo + hi) // 2
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= target:
            best = buf
            lo = q + 1
        else:
            hi = q - 1
    if best is None:
        best = BytesIO()
        img.save(best, format="JPEG", quality=75, optimize=True, progressive=True)
    best.seek(0)
    return ContentFile(best.read(), name=f"{base_name}.jpg")


def _process_one_file(uploaded_file):
    name_l = (uploaded_file.name or "photo").lower()
    ct_l = (getattr(uploaded_file, "content_type", "") or "").lower()
    if name_l.endswith((".heic", ".heif")) or ct_l in {"image/heic", "image/heif"}:
        raise ValueError("HEIC/HEIF пока не поддерживается — сохраните как JPG/PNG/WebP.")
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    try:
        orig = uploaded_file.read()
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        img.load()
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > 2560:
            r = 2560 / float(max(w, h))
            img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)
        base = name_l.rsplit("/", 1)[-1].rsplit(".", 1)[0] or "photo"
        return _encode_jpeg_to_target(img, base, orig)
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("Неподдерживаемый формат или повреждённое изображение.")

def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


def healthz_mediainfo(request):
    media_root = settings.MEDIA_ROOT
    tmp_dir = media_root / "tmp"
    probe_path = tmp_dir / "probe.txt"
    writable = False
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        probe_path.write_text("ok", encoding="utf-8")
        writable = probe_path.read_text(encoding="utf-8") == "ok"
    except Exception:
        writable = False
    finally:
        try:
            probe_path.unlink()
        except Exception:
            pass

    info = {
        "media_root": str(media_root),
        "writable": writable,
        "exists_images_dir": (media_root / "photos").exists(),
    }
    return JsonResponse(info)


def dbinfo(request):
    """
    Диагностика: путь к БД, колонки core_photo, применённые/ожидающие миграции для core.
    Закрыто @shared_key_required: GET /healthz/dbinfo/?key=kontinent
    """

    info = {}
    info["db_path"] = str(settings.DATABASES["default"]["NAME"])
    with connection.cursor() as cursor:
        try:
            desc = connection.introspection.get_table_description(cursor, "core_photo")
            info["core_photo_columns"] = [c.name for c in desc]
        except Exception as e:  # pragma: no cover - diagnostics only
            info["core_photo_columns"] = f"error: {e}"
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    applied = {f"{a}.{n}" for (a, n) in loader.applied_migrations}
    nodes = set(loader.graph.nodes.keys())
    info["applied_core_migrations"] = sorted(
        [x for x in applied if x.startswith("core.")]
    )
    info["pending_core_migrations"] = sorted(
        [
            f"{a}.{n}"
            for (a, n) in nodes
            if a == "core" and (a, n) not in loader.applied_migrations
        ]
    )
    return JsonResponse(info)


def logtail(request):
    """Return the tail of the production error log (200 lines)."""

    path = "/var/log/isty.pythonanywhere.com.error.log"
    try:
        with open(path, "r", encoding="utf-8") as f:
            tail = "".join(f.readlines()[-200:])
        return HttpResponse(tail, content_type="text/plain")
    except Exception as e:  # pragma: no cover - diagnostics only
        return HttpResponse(
            f"cannot read log: {e}",
            content_type="text/plain",
            status=500,
        )


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


def _panel_form_context(form, prop, photos):
    subtypes_map_json = json.dumps(
        getattr(form, "subtypes_map", PropertyForm.SUBTYPE_CHOICES_MAP),
        ensure_ascii=False,
    )
    return {
        "form": form,
        "prop": prop,
        "photos": photos,
        "subtypes_map_json": subtypes_map_json,
        "subtypes_placeholder": PropertyForm.SUBTYPE_PLACEHOLDER,
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
        tokens = [t for t in re.split(r"\s+", q) if t]
        for tok in tokens:
            variants = {tok, tok.lower(), tok.upper(), tok.capitalize()}
            token_q = Q()
            for variant in variants:
                token_q |= (
                    Q(title__icontains=variant)
                    | Q(address__icontains=variant)
                    | Q(external_id__icontains=variant)
                )
            props = props.filter(token_q)
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
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    form = PropertyForm()
    return render(
        request,
        "core/panel_edit.html",
        _panel_form_context(form, None, []),
    )


def panel_create(request):
    if request.method == "GET":
        initial = {
            "category": request.GET.get("category", ""),
            "operation": request.GET.get("operation", ""),
        }
        form = PropertyForm(initial=initial)
        return render(
            request,
            "core/panel_edit.html",
            _panel_form_context(form, None, []),
        )
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])
    form = PropertyForm(request.POST, request.FILES or None)
    if form.is_valid():
        prop = form.save()
        return redirect("panel_edit", pk=prop.pk)
    return render(
        request,
        "core/panel_edit.html",
        _panel_form_context(form, None, []),
        status=200,
    )


def panel_edit(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    if request.method == "POST":
        form = PropertyForm(request.POST, request.FILES or None, instance=prop)
        if form.is_valid():
            form.save()
            return redirect("panel_edit", pk=prop.pk)
        return render(
            request,
            "core/panel_edit.html",
            _panel_form_context(
                form,
                prop,
                list(prop.photos.order_by("-is_default", "sort", "id")),
            ),
            status=200,
        )
    form = PropertyForm(instance=prop)
    return render(
        request,
        "core/panel_edit.html",
        _panel_form_context(
            form,
            prop,
            list(prop.photos.order_by("-is_default", "sort", "id")),
        ),
    )


def panel_add_photo(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    if request.method != "POST":
        return redirect(f"/panel/edit/{pk}/")

    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    os.makedirs(settings.MEDIA_ROOT / "logs", exist_ok=True)

    files = list(request.FILES.getlist("images") or [])
    single = request.FILES.get("image")
    if single:
        files.append(single)

    url = (request.POST.get("full_url") or "").strip()
    make_default = bool(request.POST.get("is_default"))

    if not files and not url:
        messages.error(request, "Не выбрано ни файла, ни URL.")
        return redirect(f"/panel/edit/{pk}/")

    created = 0
    default_set = False
    max_sort = (
        Photo.objects.filter(property=prop).aggregate(Max("sort")).get("sort__max")
        or 0
    )

    for idx, uploaded in enumerate(files):
        try:
            processed = _process_one_file(uploaded)
            ph = Photo(property=prop)
            ph.image = processed
            if make_default and not default_set and idx == 0:
                Photo.objects.filter(property=prop).update(is_default=False)
                ph.is_default = True
                ph.sort = 0
                default_set = True
            else:
                max_sort += 10
                ph.sort = max_sort
            ph.save()
            created += 1
        except ValueError as e:
            log.warning("upload rejected: %s", e)
            messages.error(request, str(e))
        except Exception:
            log.exception("upload failed")
            messages.error(
                request,
                "Не удалось загрузить одно из фото (код: UnexpectedError)",
            )

    if url:
        try:
            ph = Photo(property=prop, full_url=url)
            if make_default and not default_set and created == 0:
                Photo.objects.filter(property=prop).update(is_default=False)
                ph.is_default = True
                ph.sort = 0
                default_set = True
            else:
                max_sort += 10
                ph.sort = max_sort
            ph.save()
            created += 1
        except Exception:
            log.exception("upload failed (url)")
            messages.error(request, "Не удалось добавить фото по ссылке.")

    if created:
        messages.success(request, "Фото добавлено.")
    return redirect(f"/panel/edit/{pk}/")


@require_POST
def panel_photo_delete(request, pk):
    ph = get_object_or_404(Photo, pk=pk)
    prop_id = ph.property_id
    try:
        ph.delete()
        messages.success(request, "Фото удалено.")
    except Exception:
        messages.error(request, "Не удалось удалить фото.")
    return redirect(f"/panel/edit/{prop_id}/")


@require_POST
def panel_photo_set_default(request, pk):
    ph = get_object_or_404(Photo, pk=pk)
    Photo.objects.filter(property=ph.property).update(is_default=False)
    ph.is_default = True
    ph.sort = 0
    ph.save(update_fields=["is_default", "sort"])
    messages.success(request, "Фото помечено как главное.")
    return redirect(f"/panel/edit/{ph.property_id}/")


@require_POST
@transaction.atomic
def panel_photos_reorder(request, prop_id):
    """
    Принимает order="3,1,2" — список photo.id в новом порядке.
    Все фото должны принадлежать property=prop_id.
    """

    order = (request.POST.get("order") or "").strip()
    if not order:
        messages.error(request, "Не передан порядок.")
        return redirect(f"/panel/edit/{prop_id}/")

    ids = [int(x) for x in order.split(",") if x.strip().isdigit()]
    photos = {
        p.id: p for p in Photo.objects.filter(property_id=prop_id, id__in=ids)
    }
    pos = 10
    for pid in ids:
        p = photos.get(pid)
        if p:
            p.sort = pos
            p.save(update_fields=["sort"])
            pos += 10

    messages.success(request, "Порядок фото сохранён.")
    return redirect(f"/panel/edit/{prop_id}/")

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


def _resolve_property_subtype(prop):
    return (
        getattr(prop, "subtype", None)
        or getattr(prop, "house_type", None)
        or getattr(prop, "commercial_type", None)
        or getattr(prop, "land_type", None)
    )


def export_cian(request):
    root = Element("Feed")
    SubElement(root, "Feed_Version").text = "2"  # Спецификация ЦИАН, версия 2  (см. doc)  # noqa

    # В фид попадают только отмеченные для выгрузки
    qs = (
        Property.objects.filter(export_to_cian=True, is_archived=False)
        .order_by("id")
    )

    for prop in qs:
        subtype_value = _resolve_property_subtype(prop)
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
            ordered_photos = photos_qs.order_by("-is_default", "sort", "id")
            for p in ordered_photos:
                ph = SubElement(photos_el, "PhotoSchema")
                _t(ph, "FullUrl", getattr(p, "src", ""), always=True)
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

    return HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")


def export_cian_check(request):
    qs = (
        Property.objects.filter(export_to_cian=True, is_archived=False)
        .order_by("id")
    )
    items = []

    for prop in qs:
        subtype_value = _resolve_property_subtype(prop)
        category_str = build_cian_category(
            getattr(prop, "category", ""),
            getattr(prop, "operation", ""),
            subtype_value,
        )
        missing = []

        external_id = getattr(prop, "external_id", "") or ""
        if not str(external_id).strip():
            missing.append("ExternalId")

        title = getattr(prop, "title", "") or ""
        if not str(title).strip():
            missing.append("Title")

        if not category_str:
            missing.append("Category (category/operation/subtype)")

        base_category = (getattr(prop, "category", "") or "").strip()
        if base_category in {"flat", "room", "house", "commercial"}:
            total_area = getattr(prop, "total_area", None)
            if total_area in (None, "", 0):
                missing.append("TotalArea")

        if base_category == "land":
            land_area = getattr(prop, "land_area", None)
            if land_area in (None, "", 0):
                missing.append("LandArea")

        items.append(
            {
                "prop": prop,
                "category": category_str,
                "missing": missing,
            }
        )

    return render(request, "core/cian_check.html", {"items": items})

