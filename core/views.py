# core/views.py
import json
import logging
import os
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Optional
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import FieldDoesNotExist
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models import Max, Q
from django.http import (
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

try:
    from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError
except ImportError:  # pragma: no cover - support for trimmed Pillow stub
    from PIL import Image  # type: ignore

    class _StubImageFile:  # pragma: no cover - minimal stub
        LOAD_TRUNCATED_IMAGES = False

    ImageFile = _StubImageFile  # type: ignore

    class UnidentifiedImageError(Exception):
        pass

    class _StubImageOps:  # pragma: no cover - minimal stub
        @staticmethod
        def exif_transpose(img):
            return img

    ImageOps = _StubImageOps()  # type: ignore

from .cian import build_cian_feed, resolve_category
from .forms import PropertyForm, fields_for_category, group_fields
from .models import Photo, Property
from .utils.image_pipeline import InvalidImage, compress_to_jpeg


log = logging.getLogger("upload")
ImageFile.LOAD_TRUNCATED_IMAGES = True

INVALID_IMAGE_MESSAGE = "Неподдерживаемый формат или повреждённое изображение."


def _ensure_migrated():
    """Best-effort auto-migrate in preview/PR containers to avoid 500 errors."""

    if os.getenv("AUTO_APPLY_MIGRATIONS", "0") != "1":
        return

    loader = MigrationLoader(connection, ignore_no_migrations=True)
    nodes = set(loader.graph.nodes.keys())
    if any((app_label, migration_name) not in loader.applied_migrations for app_label, migration_name in nodes):
        try:
            call_command("migrate", interactive=False, run_syncdb=True, verbosity=0)
        except Exception:
            # Races are fine if multiple workers call this concurrently.
            pass


def _short_category(prop) -> str:
    category = (getattr(prop, "category", "") or "").strip().lower()
    if category in {"flat", "apartment", "квартира"}:
        rooms = (
            getattr(prop, "flat_rooms_count", None)
            or getattr(prop, "rooms", None)
            or getattr(prop, "rooms_for_sale_count", None)
        )
        try:
            rooms_int = int(rooms)
        except (TypeError, ValueError):
            rooms_int = None
        if rooms_int:
            return f"{rooms_int}к кв."
        studio_flags = (
            getattr(prop, "is_studio", None),
            getattr(prop, "flat_type", None),
        )
        if any(str(flag).lower() in {"1", "true", "yes", "studio"} for flag in studio_flags if flag not in (None, "")):
            return "ст кв."
        return "Кв."
    mapping = {
        "house": "Дом",
        "дом": "Дом",
        "room": "Комн.",
        "комната": "Комн.",
        "land": "Зем.",
        "земля": "Зем.",
        "commercial": "Ком.",
        "коммерция": "Ком.",
        "garage": "Гар.",
        "гараж": "Гар.",
    }
    if category in mapping:
        return mapping[category]
    return category[:1].upper() + category[1:] if category else ""


def _compact_address(prop) -> str:
    ref_city = "Новокузнецк"

    locality = (getattr(prop, "locality", "") or "").strip()
    city = (getattr(prop, "city", "") or "").strip()
    street = (getattr(prop, "street", "") or "").strip()
    house = (getattr(prop, "house_number", "") or getattr(prop, "house", "") or "").strip()
    apartment = (
        getattr(prop, "apartment", "")
        or getattr(prop, "flat_number", "")
        or getattr(prop, "flat", "")
        or ""
    ).strip()
    base_address = (getattr(prop, "address", "") or "").strip()

    if not street and not house and base_address:
        street = base_address

    cleaned_base = re.sub(
        r"(?:г\.?\s*)?Новокузнецк,?",
        "",
        base_address,
        flags=re.IGNORECASE,
    )
    cleaned_base = re.sub(r"\s+", " ", cleaned_base).strip(", ").strip()

    locality_part = ""
    for candidate in (locality, city):
        if candidate and candidate != ref_city:
            locality_part = candidate
            break

    house_part = house
    if apartment:
        suffix = f"-{apartment}"
        house_part = f"{house}{suffix}" if house else apartment

    parts = [street, house_part]
    tail = ", ".join([piece for piece in parts if piece])
    components = [comp for comp in (locality_part, tail) if comp]

    if components:
        return ", ".join(components)

    return cleaned_base


def _format_price_compact(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        quantized = Decimal(value)
    except (InvalidOperation, TypeError):
        return "—"
    amount = int(quantized)
    return f"{amount:,}".replace(",", " ")


def _format_phone_10(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 10:
        return ""
    digits = digits[-10:]
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:8]}-{digits[8:]}"


def _format_date(dt) -> str:
    if not dt:
        return ""
    try:
        dt_value = timezone.localtime(dt)
    except (ValueError, TypeError, AttributeError):
        dt_value = dt
    return dt_value.strftime("%d.%m.%y")


def _format_price(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        quantized = Decimal(value)
    except (InvalidOperation, TypeError):
        return "—"
    amount = int(quantized)
    return f"{amount:,}".replace(",", " ") + " ₽"


def _pillow_supports_rotation() -> bool:
    image_cls = getattr(Image, "Image", None)
    if image_cls is None:
        return False
    module_requirements = ("open", "new")
    if any(not hasattr(Image, attr) for attr in module_requirements):
        return False
    instance_requirements = ("rotate", "transpose", "convert", "getexif")
    if any(not hasattr(image_cls, attr) for attr in instance_requirements):
        return False
    exif_transpose = getattr(ImageOps, "exif_transpose", None)
    return callable(exif_transpose)


def _image_has_rotation_api(img) -> bool:
    required = ("rotate", "transpose", "convert", "getexif")
    for attr in required:
        if not hasattr(img, attr):
            return False
    return True


def _check_decoder_available(kind: str) -> bool:
    """Return True if Pillow reports decoder support for *kind* ("jpeg"/"webp"/"png")."""

    # Try Pillow's features API first
    try:  # pragma: no branch - optional dependency
        from PIL import features as pil_features  # type: ignore

        probes_map = {
            "jpeg": ("jpeg", "jpg", "libjpeg", "libjpeg_turbo"),
            "webp": ("webp",),
            "png": ("zlib", "libpng", "png"),
        }
        for probe in probes_map.get(kind, ()):  # pragma: no branch - small tuple
            try:
                if pil_features.check(probe):
                    return True
            except Exception:  # pragma: no cover - defensive
                continue
        if kind in probes_map:
            return False
    except ImportError:  # pragma: no cover - stub Pillow shipped in tests
        pass

    # Fall back to registered extensions when features API is unavailable
    registered = getattr(Image, "registered_extensions", None)
    if callable(registered):
        try:
            mapping = {
                ext.lower(): handler for ext, handler in registered().items()  # type: ignore[arg-type]
            }
            if kind == "jpeg":
                return any(ext in mapping for ext in (".jpg", ".jpeg"))
            if kind == "webp":
                return ".webp" in mapping
            if kind == "png":
                return ".png" in mapping
        except Exception:  # pragma: no cover - defensive
            pass

    # Assume supported when we cannot determine availability explicitly
    return True


def _guess_decoder_kind(name_l: str, ct_l: str) -> Optional[str]:
    jpeg_exts = (".jpg", ".jpeg")
    webp_exts = (".webp",)
    png_exts = (".png",)
    if name_l.endswith(webp_exts) or ct_l in {"image/webp", "image/x-webp"}:
        return "webp"
    if name_l.endswith(jpeg_exts) or ct_l in {"image/jpeg", "image/pjpeg"}:
        return "jpeg"
    if name_l.endswith(png_exts) or ct_l == "image/png":
        return "png"
    return None


def _looks_like_image(kind: str, payload: bytes) -> bool:
    if not payload:
        return False
    if kind == "jpeg":
        return payload.startswith(b"\xFF\xD8")
    if kind == "webp":
        return len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
    if kind == "png":
        return payload.startswith(b"\x89PNG\r\n\x1a\n")
    return True


def _fallback_file_name(original: Optional[str], kind: str) -> str:
    if original:
        return original
    if kind == "webp":
        suffix = ".webp"
    elif kind == "png":
        suffix = ".png"
    else:
        suffix = ".jpg"
    return f"photo{suffix}"


def _encode_jpeg_to_target(img, base_name, orig_bytes):
    target = max(150 * 1024, len(orig_bytes) // 5)  # ≈×5, но не меньше ~150KB
    lo, hi, best = 65, 90, None
    while lo <= hi:
        q = (lo + hi) // 2
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= target:
            best, lo = buf, q + 1
        else:
            hi = q - 1
    if best is None:
        best = BytesIO()
        img.save(best, format="JPEG", quality=75, optimize=True, progressive=True)
    best.seek(0)
    return ContentFile(best.read(), name=f"{base_name}.jpg")


def _process_one_file(uploaded_file):
    """
    Для JPEG/PNG/WEBP: всегда раскодировать через Pillow и перекодировать в JPEG с целевым размером.
    Для HEIC/HEIF — вернуть явную ошибка-строку (требуется тестами).
    Для совсем мусора/битого — тоже явная ошибка-строку.
    """
    name_l = (uploaded_file.name or "photo").lower()
    ct_l = (getattr(uploaded_file, "content_type", "") or "").lower()
    # HEIC/HEIF — сразу отказ с нужной формулировкой
    if name_l.endswith((".heic", ".heif")) or ct_l in {"image/heic", "image/heif"}:
        raise ValueError("HEIC/HEIF пока не поддерживается — сохраните как JPG/PNG/WebP.")
    try:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        orig = uploaded_file.read()
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        data = compress_to_jpeg(orig)
        base = name_l.rsplit("/", 1)[-1].rsplit(".", 1)[0] or "photo"
        return ContentFile(data, name=f"{base}.jpg")
    except InvalidImage:
        raise ValueError(INVALID_IMAGE_MESSAGE)

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
    if form.is_bound:
        category_value = form.data.get("category", "")
        operation_value = form.data.get("operation", "")
    else:
        category_value = form.initial.get("category", "") if form.initial else ""
        operation_value = form.initial.get("operation", "") if form.initial else ""

    if not category_value and getattr(form.instance, "category", None):
        category_value = form.instance.category
    if not operation_value and getattr(form.instance, "operation", None):
        operation_value = form.instance.operation

    category_value = (category_value or "").strip()
    operation_value = (operation_value or "").strip()

    cat_fields = fields_for_category(category_value, operation_value)
    cat_fields = [name for name in cat_fields if name in form.fields]

    field_groups, category_misc = group_fields(cat_fields, category_value)

    bound_groups = []
    for title, names in field_groups:
        bound_fields = [form[name] for name in names if name in form.fields]
        if bound_fields:
            bound_groups.append((title, bound_fields))

    category_misc_bound = [form[name] for name in category_misc if name in form.fields]
    # Показываем в «Прочем» только хвост категорийных полей. Остальные поля либо
    # выводятся в явных секциях шаблона, либо сознательно скрыты.
    field_fallback = category_misc_bound
    return {
        "form": form,
        "prop": prop,
        "photos": photos,
        "subtypes_map_json": subtypes_map_json,
        "subtypes_placeholder": PropertyForm.SUBTYPE_PLACEHOLDER,
        "field_groups": bound_groups,
        "field_fallback": field_fallback,
    }


def panel_list(request):
    _ensure_migrated()

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
    props_list = list(props)

    rows = []
    for prop in props_list:
        floor_number = getattr(prop, "floor_number", None)
        building_floors = getattr(prop, "building_floors", None)
        has_floor = floor_number not in (None, "")
        has_building_floors = building_floors not in (None, "")
        if has_floor and has_building_floors:
            floors_display = f"{floor_number}/{building_floors}"
        elif has_floor:
            floors_display = str(floor_number)
        elif has_building_floors:
            floors_display = f"—/{building_floors}"
        else:
            floors_display = ""

        price_value = getattr(prop, "price", None)
        raw_price = ""
        if price_value not in (None, ""):
            try:
                raw_price = str(int(Decimal(price_value)))
            except (InvalidOperation, TypeError, ValueError):
                raw_price = ""

        rows.append(
            {
                "id": prop.pk,
                "type": _short_category(prop),
                "address": _compact_address(prop) or (getattr(prop, "address", "") or ""),
                "full_address": getattr(prop, "address", "") or "",
                "external_id": getattr(prop, "external_id", "") or "",
                "floors": floors_display,
                "created": _format_date(getattr(prop, "created_at", None)),
                "updated": _format_date(getattr(prop, "updated_at", None)),
                "price_display": _format_price_compact(price_value),
                "price_raw": raw_price,
                "is_archived": bool(getattr(prop, "is_archived", False)),
                "export_to_cian": bool(getattr(prop, "export_to_cian", False)),
                "export_to_domklik": bool(getattr(prop, "export_to_domklik", False)),
            }
        )

    show_archived_flag = include_archived or show == "all"
    return render(
        request,
        "core/panel_list.html",
        {
            "rows": rows,
            "q": q,
            "show": show,
            "include_archived": show_archived_flag,
        },
    )


@require_POST
def panel_update_price(request, pk):
    _ensure_migrated()
    prop = get_object_or_404(Property, pk=pk)

    raw = (request.POST.get("price") or "").strip()
    if not raw:
        prop.price = None
        prop.save(update_fields=["price", "updated_at"])
        formatted = _format_price_compact(prop.price)
        return JsonResponse({"ok": True, "price": "", "price_display": formatted, "price_formatted": formatted})

    digits = re.sub(r"\D", "", raw)
    if not digits:
        return JsonResponse({"ok": False, "error": "invalid_price"}, status=400)

    try:
        value = Decimal(digits)
    except (InvalidOperation, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_price"}, status=400)

    prop.price = value
    prop.save(update_fields=["price", "updated_at"])

    formatted = _format_price_compact(prop.price)
    return JsonResponse({"ok": True, "price": str(prop.price), "price_display": formatted, "price_formatted": formatted})


@require_POST
def panel_toggle_archive(request, pk):
    _ensure_migrated()
    prop = get_object_or_404(Property, pk=pk)
    prop.is_archived = not prop.is_archived
    prop.status = "archived" if prop.is_archived else "active"
    prop.save(update_fields=["is_archived", "status", "updated_at"])
    return JsonResponse({"ok": True, "is_archived": prop.is_archived})


@require_POST
def panel_toggle_export_cian(request, pk: int):
    _ensure_migrated()
    prop = get_object_or_404(Property, pk=pk)
    prop.export_to_cian = not bool(prop.export_to_cian)
    prop.save(update_fields=["export_to_cian", "updated_at"])
    return JsonResponse({"ok": True, "export_to_cian": prop.export_to_cian})


@require_POST
def panel_toggle_export_dom(request, pk: int):
    _ensure_migrated()
    prop = get_object_or_404(Property, pk=pk)
    prop.export_to_domklik = not bool(prop.export_to_domklik)
    prop.save(update_fields=["export_to_domklik", "updated_at"])
    return JsonResponse({"ok": True, "export_to_domklik": prop.export_to_domklik})


@require_POST
def panel_delete(request, pk):
    _ensure_migrated()
    prop = get_object_or_404(Property, pk=pk)
    prop.delete()
    return JsonResponse({"ok": True, "deleted": True})

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
    _ensure_migrated()
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

    media_root = Path(settings.MEDIA_ROOT)
    os.makedirs(media_root, exist_ok=True)
    os.makedirs(media_root / "logs", exist_ok=True)

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
            if make_default and not default_set:
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
def panel_photo_rotate(request, pk):
    direction = (request.GET.get("dir") or "").lower()
    if direction not in {"left", "right"}:
        return JsonResponse({"ok": False, "error": "invalid_direction"}, status=400)

    if not _pillow_supports_rotation():
        return JsonResponse({"ok": False, "error": "rotate_unsupported"})

    photo = get_object_or_404(Photo, pk=pk)
    if not photo.image:
        return JsonResponse({"ok": False, "error": "no_local_image"}, status=400)

    try:
        photo.image.open("rb")
        original_bytes = photo.image.read()
    finally:
        try:
            photo.image.close()
        except Exception:
            pass

    try:
        img = Image.open(BytesIO(original_bytes))
        img.load()
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_image"}, status=400)

    if not _image_has_rotation_api(img):
        return JsonResponse({"ok": False, "error": "rotate_unsupported"})

    angle = -90 if direction == "left" else 90
    rotated = img.rotate(angle, expand=True)
    rotated = rotated.convert("RGB")

    buf = BytesIO()
    rotated.save(buf, format="JPEG", optimize=True, progressive=True, quality=85)
    data = buf.getvalue()

    storage = getattr(photo.image, "storage", None)
    name = getattr(photo.image, "name", None)
    target_name = name or photo.image.name
    if not target_name:
        target_name = photo.image.field.generate_filename(photo, f"photo-{photo.id}.jpg")

    if storage and name:
        try:
            storage.delete(name)
        except Exception:
            pass

    try:
        photo.image.save(target_name, ContentFile(data), save=False)
        photo.save(update_fields=["image"])
    except Exception:
        return JsonResponse({"ok": False, "error": "save_failed"}, status=500)

    return JsonResponse({"ok": True, "id": photo.id})


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


@require_POST
def panel_photos_bulk_delete(request):
    ids = request.POST.getlist("ids[]") or request.POST.getlist("ids")
    property_id = request.POST.get("property_id")

    try:
        id_values = [int(x) for x in ids if str(x).isdigit()]
    except Exception:
        id_values = []

    if not property_id or not id_values:
        return JsonResponse({"ok": False, "error": "invalid_payload"}, status=400)

    prop = get_object_or_404(Property, pk=property_id)
    qs = Photo.objects.filter(property=prop, id__in=id_values)
    deleted_ids = []
    for item in qs:
        deleted_ids.append(item.id)
        item.delete()

    return JsonResponse({"ok": True, "deleted": deleted_ids})

def export_cian(request):
    _ensure_migrated()
    # В фид попадают только отмеченные для выгрузки
    qs = (
        Property.objects.filter(export_to_cian=True, is_archived=False)
        .order_by("id")
        .prefetch_related("photos")
    )
    feed_result = build_cian_feed(qs)
    xml_bytes = feed_result.xml

    strict_mode = (request.GET.get("strict") or "").strip() == "1"
    if settings.DEBUG or strict_mode:
        uncovered = [
            (result.prop, sorted(result.uncovered_fields))
            for result in feed_result.objects
            if result.uncovered_fields
        ]
        if uncovered:
            export_log = logging.getLogger("core.cian.export")
            for prop_obj, fields in uncovered:
                identifier = getattr(prop_obj, "external_id", None) or getattr(
                    prop_obj, "pk", None
                )
                export_log.warning(
                    "CIAN export uncovered fields for %s: %s",
                    identifier,
                    ", ".join(fields),
                )

    feeds_dir = os.path.join(settings.MEDIA_ROOT, "feeds")
    os.makedirs(feeds_dir, exist_ok=True)
    out_path = os.path.join(feeds_dir, "cian.xml")
    with open(out_path, "wb") as fh:
        fh.write(xml_bytes)

    return HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")


def export_domklik(request):
    _ensure_migrated()
    qs = (
        Property.objects.filter(export_to_domklik=True, is_archived=False)
        .order_by("id")
        .prefetch_related("photos")
    )
    feed_result = build_cian_feed(qs)
    xml_bytes = feed_result.xml

    feeds_dir = os.path.join(settings.MEDIA_ROOT, "feeds")
    os.makedirs(feeds_dir, exist_ok=True)
    out_path = os.path.join(feeds_dir, "domklik.xml")
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
        category_str = resolve_category(prop)
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

        # Новые проверки
        # хотя бы один телефон
        num1 = (getattr(prop, "phone_number", "") or "").strip()
        num2 = (getattr(prop, "phone_number2", "") or "").strip()
        if not (num1 or num2):
            missing.append("Phone (at least one)")
        # хотя бы одно фото
        photos_qs = getattr(prop, "photos", None)
        if not (photos_qs and photos_qs.exists()):
            missing.append("Photo (at least one)")
        # цена обязательна для продажи
        if (getattr(prop, "operation", "") or "").strip() == "sale":
            price = getattr(prop, "price", None)
            if price in (None, "", 0):
                missing.append("Price")

        items.append(
            {
                "prop": prop,
                "category": category_str,
                "missing": missing,
            }
        )

    return render(request, "core/cian_check.html", {"items": items})

