from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, tostring

try:  # pragma: no cover - optional dependency is used when available
    import yaml  # type: ignore
except Exception:  # pragma: no cover - fallback parser is used
    yaml = None
from django.conf import settings
from django.utils.encoding import smart_str

from .subtypes import CATEGORY_TO_SUBTYPE_FIELD, PROPERTY_SUBTYPE_CHOICES

log = logging.getLogger(__name__)


def _strip_yaml_comments(line: str) -> str:
    result: list[str] = []
    in_quote: str | None = None
    for index, ch in enumerate(line):
        if in_quote:
            result.append(ch)
            if ch == in_quote and (index == 0 or line[index - 1] != "\\"):
                in_quote = None
        else:
            if ch in {'"', "'"}:
                in_quote = ch
                result.append(ch)
            elif ch == '#':
                break
            else:
                result.append(ch)
    return ''.join(result).rstrip()


def _parse_scalar(value: str):
    text = value.strip()
    if text == '':
        return ''
    lowered = text.lower()
    if lowered == 'null':
        return None
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return text[1:-1]
    return text


def _parse_block(lines: list[str], start: int, indent: int):
    items: list[object] = []
    mapping: dict[str, object] = {}
    index = start

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        current_indent = len(line) - len(line.lstrip(' '))
        if current_indent < indent:
            break
        stripped = line.strip()
        if stripped.startswith('- '):
            if mapping:
                raise ValueError('Mixed list and dict structures are not supported')
            item_text = stripped[2:].strip()
            if item_text:
                items.append(_parse_scalar(item_text))
                index += 1
            else:
                value, index = _parse_block(lines, index + 1, current_indent + 2)
                items.append(value)
        else:
            if items:
                raise ValueError('Mixed list and dict structures are not supported')
            if ':' not in stripped:
                raise ValueError(f'Invalid YAML line: {stripped}')
            key, value_text = stripped.split(':', 1)
            key = key.strip()
            value_text = value_text.strip()
            if value_text:
                mapping[key] = _parse_scalar(value_text)
                index += 1
            else:
                value, index = _parse_block(lines, index + 1, current_indent + 2)
                mapping[key] = value

    return (items if items else mapping), index


def _simple_yaml_load(text: str):
    cleaned = [_strip_yaml_comments(line) for line in text.splitlines()]
    filtered = [line for line in cleaned if line.strip()]
    value, _ = _parse_block(filtered, 0, 0)
    return value


@dataclass(frozen=True)
class AdBuildResult:
    """Payload produced for a single property object."""

    prop: object
    element: Element
    filled_fields: Set[str]
    exported_fields: Set[str]

    @property
    def uncovered_fields(self) -> Set[str]:
        return self.filled_fields - self.exported_fields


@dataclass(frozen=True)
class FeedBuildResult:
    """Container describing the generated feed and coverage metadata."""

    xml: bytes
    objects: Sequence[AdBuildResult]


_REGISTRY: Optional[Dict] = None


def load_registry() -> Dict:
    global _REGISTRY
    if _REGISTRY is None:
        registry_path = Path(settings.BASE_DIR) / "docs" / "cian_map.yaml"
        with registry_path.open("r", encoding="utf-8") as fh:
            text = fh.read()
        if yaml is not None:
            _REGISTRY = yaml.safe_load(text)
        else:  # pragma: no cover - exercised when PyYAML is unavailable
            _REGISTRY = _simple_yaml_load(text)
    return _REGISTRY  # type: ignore[return-value]


def resolve_category(prop) -> str:
    """Return registry category name for a Property instance."""

    category = smart_str(getattr(prop, "category", "")).strip().lower()
    operation = smart_str(getattr(prop, "operation", "")).strip().lower()

    if category == "flat" and operation.startswith("rent"):
        return "flatRent"
    if category == "room":
        if operation in {"rent_long", "rent_daily"}:
            return "roomRent"
        if operation == "sale":
            return "roomSale"

    mapping = {
        "flat": "flatSale",
        "house": "houseSale",
        "land": "landSale",
        "commercial": "commercialSale",
        "garage": "garageSale",
    }
    if category == "room":
        return "roomSale"
    return mapping.get(category, "flatSale")


def _ensure_child(parent: Element, tag: str) -> Element:
    for child in parent:
        if child.tag == tag:
            return child
    return SubElement(parent, tag)


def emit(parent: Element, path: str, value: str) -> None:
    """Create nested XML nodes according to dotted path and set value."""

    parts = [part for part in path.split(".") if part]
    if not parts:
        return

    node = parent
    for tag in parts[:-1]:
        node = _ensure_child(node, tag)
    leaf = _ensure_child(node, parts[-1])
    leaf.text = smart_str(value)


def _normalize_decimal(value) -> str:
    quant = Decimal(str(value))
    normalized = quant.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def map_value(field: str, raw) -> Optional[str]:
    registry = load_registry()
    values_map = registry.get("values", {}).get(field, {})
    if values_map:
        raw_str = smart_str(raw).strip()
        for candidate in (raw, raw_str, raw_str.lower()):
            if candidate in values_map:
                mapped = values_map[candidate]
                if mapped is None:
                    return None
                return smart_str(mapped)
        if raw_str and raw_str.lower() in values_map:
            mapped = values_map[raw_str.lower()]
            if mapped is None:
                return None
            return smart_str(mapped)

    if isinstance(raw, bool):
        return "true" if raw else "false"
    if isinstance(raw, Decimal):
        return _normalize_decimal(raw)
    if isinstance(raw, (float, int)):
        return _normalize_decimal(raw)
    return smart_str(raw)


def _value_is_present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value is True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Decimal):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _collect_filled_fields(prop, stop_fields: Set[str]) -> Set[str]:
    filled: Set[str] = set()
    for field in prop._meta.concrete_fields:  # type: ignore[attr-defined]
        name = field.name
        if name in stop_fields:
            continue
        if _value_is_present(getattr(prop, name, None)):
            filled.add(name)
    # phone country is meaningful only when there is at least one number
    if not any(
        _value_is_present(getattr(prop, attr, None))
        for attr in ("phone_number", "phone_number2")
    ):
        filled.discard("phone_country")
    return filled


def _digits_only(value: Optional[str]) -> str:
    if not value:
        return ""
    return "".join(ch for ch in smart_str(value) if ch.isdigit())


def _normalize_phone_number(raw: Optional[str], country: str) -> Optional[str]:
    digits = _digits_only(raw)
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = digits[1:]
    if country == "7" and len(digits) == 11 and digits.startswith("7"):
        digits = digits[1:]
    if len(digits) < 10 or len(digits) > 11:
        return None
    if country == "7" and len(digits) != 10:
        return None
    return digits


def _absolute_url(path: Optional[str]) -> str:
    value = smart_str(path or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return value
    base = smart_str(getattr(settings, "SITE_BASE_URL", "")).strip().rstrip("/")
    if not base:
        return value
    return urljoin(f"{base}/", value.lstrip("/"))


def _resolve_photo_url(photo) -> str:
    full_url = getattr(photo, "full_url", None)
    absolute = _absolute_url(full_url)
    if absolute:
        return absolute
    image = getattr(photo, "image", None)
    if image:
        try:
            image_url = smart_str(image.url)
        except Exception:
            image_url = ""
        if image_url:
            return _absolute_url(image_url)
    return ""


def _collect_photos(prop) -> List[Tuple[str, bool]]:
    photos_attr = getattr(prop, "photos", None)
    if not photos_attr:
        return []
    queryset = photos_attr.all()
    model_meta = getattr(getattr(queryset, "model", None), "_meta", None)
    ordering = getattr(model_meta, "ordering", None)
    if ordering:
        queryset = queryset.order_by(*ordering)
    result: List[Tuple[str, bool]] = []
    seen: Set[str] = set()
    for photo in queryset:
        url = _resolve_photo_url(photo)
        if not url or url in seen:
            continue
        seen.add(url)
        result.append((url, bool(getattr(photo, "is_default", False))))
    return result


def _build_phones(parent: Element, prop, exported_fields: Set[str]) -> None:
    registry = load_registry()
    phone_specs = registry.get("common", {}).get("phones", [])
    if not phone_specs:
        return

    country_raw = getattr(prop, "phone_country", None)
    country_digits = _digits_only(country_raw) or "7"
    country = f"+{country_digits}"

    numbers: List[Tuple[str, str]] = []
    for field_name in ("phone_number", "phone_number2"):
        normalized = _normalize_phone_number(
            getattr(prop, field_name, None), country_digits
        )
        if normalized:
            numbers.append((field_name, normalized))

    if not numbers:
        return

    phones_el = _ensure_child(parent, "Phones")
    for field_name, number in numbers[:2]:
        schema = SubElement(phones_el, "PhoneSchema")
        SubElement(schema, "CountryCode").text = country
        SubElement(schema, "Number").text = number
        exported_fields.add(field_name)

    exported_fields.add("phone_country")


def _build_photos(parent: Element, prop, exported_fields: Set[str]) -> None:
    layout_url = _absolute_url(getattr(prop, "layout_photo_url", None))
    if layout_url:
        layout = _ensure_child(parent, "LayoutPhoto")
        _ensure_child(layout, "FullUrl").text = layout_url
        exported_fields.add("layout_photo_url")

    photos = _collect_photos(prop)
    if not photos:
        return

    photos_el = _ensure_child(parent, "Photos")
    default_assigned = False
    for url, is_default in photos:
        schema = SubElement(photos_el, "PhotoSchema")
        SubElement(schema, "FullUrl").text = url
        if not default_assigned and is_default:
            SubElement(schema, "IsDefault").text = "true"
            default_assigned = True

    if photos and not default_assigned:
        first_schema = photos_el.find("PhotoSchema")
        if first_schema is not None:
            SubElement(first_schema, "IsDefault").text = "true"


def build_ad_xml(prop) -> AdBuildResult:
    registry = load_registry()
    stop_fields = set(registry.get("stop_fields", []))
    category_name = resolve_category(prop)

    element = Element("object")
    emit(element, "Category", category_name)

    filled_fields = _collect_filled_fields(prop, stop_fields)
    exported_fields: Set[str] = set()

    fallback_values: Dict[str, str] = {}
    subtype_helper = smart_str(getattr(prop, "subtype", "")).strip()
    category_raw = smart_str(getattr(prop, "category", "")).strip().lower()
    if subtype_helper and category_raw:
        allowed_values = {
            value for value, _ in PROPERTY_SUBTYPE_CHOICES.get(category_raw, [])
        }
        if not allowed_values or subtype_helper in allowed_values:
            target_field = CATEGORY_TO_SUBTYPE_FIELD.get(category_raw)
            if target_field and not _value_is_present(getattr(prop, target_field, None)):
                fallback_values[target_field] = subtype_helper

    rooms_count_value = getattr(prop, "rooms", None)
    if not _value_is_present(rooms_count_value):
        flat_rooms_value = getattr(prop, "flat_rooms_count", None)
        if _value_is_present(flat_rooms_value):
            fallback_values["rooms"] = flat_rooms_value

    values_registry: Dict[str, Dict] = registry.get("values", {})

    def _process(fields_map: Dict[str, object]) -> None:
        for field_name, path in fields_map.items():
            if field_name == "agent_bonus_is_percent":
                bonus_value = getattr(prop, "agent_bonus_value", None)
                if not _value_is_present(bonus_value):
                    continue

            raw_value = getattr(prop, field_name, None)
            if field_name in fallback_values and not _value_is_present(raw_value):
                raw_value = fallback_values[field_name]
            values_map: Dict = values_registry.get(field_name, {})

            if not _value_is_present(raw_value):
                should_continue = True
                if values_map and raw_value is not None:
                    raw_str = smart_str(raw_value).strip()
                    candidates = [raw_value]
                    if raw_str:
                        candidates.append(raw_str)
                        candidates.append(raw_str.lower())
                    for candidate in candidates:
                        if candidate in values_map:
                            should_continue = False
                            break
                if should_continue:
                    continue

            mapped_value = map_value(field_name, raw_value)
            if mapped_value in (None, ""):
                continue

            if isinstance(path, (list, tuple)):
                paths_to_emit: List[str] = []
                for sub_path in path:
                    sub_path_str = smart_str(sub_path)
                    if (
                        sub_path_str == "BargainTerms.AgentBonus.Currency"
                        and not exported_fields.intersection(
                            {"agent_bonus_value", "agent_bonus_is_percent"}
                        )
                    ):
                        continue
                    paths_to_emit.append(sub_path_str)
            else:
                paths_to_emit = [smart_str(path)]

            if not paths_to_emit:
                continue

            for sub_path in paths_to_emit:
                emit(element, sub_path, mapped_value)
            exported_fields.add(field_name)

    common_fields = registry.get("common", {}).get("fields", {})
    _process(common_fields)

    deal_terms_fields = registry.get("deal_terms", {}).get("fields", {})
    _process(deal_terms_fields)

    category_fields = (
        registry.get("categories", {})
        .get(category_name, {})
        .get("fields", {})
    )
    _process(category_fields)

    _build_phones(element, prop, exported_fields)
    _build_photos(element, prop, exported_fields)

    for helper_field in ("category", "operation", "subtype"):
        if helper_field in filled_fields:
            exported_fields.add(helper_field)

    return AdBuildResult(
        prop=prop,
        element=element,
        filled_fields=filled_fields,
        exported_fields=exported_fields,
    )


def build_cian_feed(properties: Iterable) -> FeedBuildResult:
    root = Element("feed")
    SubElement(root, "feed_version").text = "2"

    objects: List[AdBuildResult] = []
    for prop in properties:
        result = build_ad_xml(prop)
        root.append(result.element)
        objects.append(result)

    xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
    return FeedBuildResult(xml=xml_bytes, objects=objects)


def build_cian_feed_xml(properties: Iterable) -> bytes:
    return build_cian_feed(properties).xml


__all__ = [
    "AdBuildResult",
    "FeedBuildResult",
    "build_ad_xml",
    "build_cian_feed",
    "build_cian_feed_xml",
    "emit",
    "load_registry",
    "map_value",
    "resolve_category",
]
