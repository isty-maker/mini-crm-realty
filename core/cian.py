from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Sequence
from urllib.parse import urljoin

from django.conf import settings
from django.utils.encoding import smart_str

try:  # pragma: no cover - optional dependency
    from django.contrib.sites.models import Site
except Exception:  # pragma: no cover - sites may be disabled
    Site = None

from xml.etree.ElementTree import Element, SubElement, tostring


HOUSE_GAS_MAP = {
    "main_on_plot": "main",
    "gasholder": "gasHolder",
    "border": "border",
}

HOUSE_DRAINAGE_MAP = {
    "central": "central",
    "septic": "septicTank",
    "cesspool": "cesspool",
}

HOUSE_WATER_MAP = {
    "central": "central",
    "borehole": "borehole",
    "well": "well",
}


def _clean(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _is_rent(operation: str) -> bool:
    return operation.startswith("rent")


def build_cian_category(category: Optional[str], operation: Optional[str], subtype: Optional[str]) -> str:
    cat = _clean(category)
    op = _clean(operation)
    sub = _clean(subtype)

    default = "flatSale"
    if not cat:
        return default

    if cat == "flat":
        return "flatRent" if _is_rent(op) else "flatSale"

    if cat == "room":
        return "roomRent" if _is_rent(op) else "roomSale"

    if cat == "house":
        return "houseRent" if _is_rent(op) else "houseSale"

    if cat == "commercial":
        sale_map = {
            "office": "officeSale",
            "retail": "retailSale",
            "warehouse": "warehouseSale",
            "production": "productionSale",
            "free_purpose": "freeUseSale",
        }
        rent_map = {
            "office": "officeRent",
            "retail": "retailRent",
            "warehouse": "warehouseRent",
            "production": "productionRent",
            "free_purpose": "freeUseRent",
        }
        if _is_rent(op):
            return rent_map.get(sub, "commercialRent")
        return sale_map.get(sub, "commercialSale")

    if cat == "land":
        if op == "sale":
            return "landSale"
        if _is_rent(op):
            return "landRent"
        return default

    if cat == "garage":
        if op == "sale":
            return "garageSale"
        if _is_rent(op):
            return "garageRent"
        return default

    return default


def _ensure_leading_slash(path: str) -> str:
    if not path:
        return path
    if path.startswith("/"):
        return path
    return f"/{path.lstrip('/')}"


def build_absolute_url(path: Optional[str], request=None) -> str:
    """Return an absolute http(s) URL for the provided path."""

    if not path:
        return ""

    value = smart_str(path).strip()
    if not value:
        return ""

    lowered = value.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return value

    if value.startswith("//"):
        scheme = "https"
        if getattr(settings, "SECURE_SSL_REDIRECT", False) or getattr(
            settings, "SESSION_COOKIE_SECURE", False
        ):
            scheme = "https"
        return f"{scheme}:{value}"

    base_url = smart_str(getattr(settings, "FEED_PUBLIC_BASE_URL", "")).strip().rstrip("/")
    normalized_path = _ensure_leading_slash(value)

    if base_url:
        return urljoin(f"{base_url}/", normalized_path.lstrip("/"))

    if request is not None:
        return request.build_absolute_uri(normalized_path)

    site_base = smart_str(getattr(settings, "SITE_BASE_URL", "")).strip().rstrip("/")
    if site_base:
        return urljoin(f"{site_base}/", normalized_path.lstrip("/"))

    if Site is not None:
        try:
            current_site = Site.objects.get_current()
            domain = smart_str(getattr(current_site, "domain", "")).strip().strip("/")
            if domain:
                scheme = "https" if getattr(settings, "SESSION_COOKIE_SECURE", False) else "http"
                return urljoin(f"{scheme}://{domain}/", normalized_path.lstrip("/"))
        except Exception:
            pass

    return normalized_path


def _digits_only(value: Optional[str]) -> str:
    if not value:
        return ""
    return "".join(ch for ch in smart_str(value) if ch.isdigit())


def _is_http_url(value: str) -> bool:
    lower = value.lower()
    return lower.startswith("http://") or lower.startswith("https://")


def _normalize_phone_number(value: Optional[str], country_code: str) -> Optional[str]:
    digits = _digits_only(value)
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = digits[1:]
    if country_code == "7" and len(digits) == 11 and digits.startswith("7"):
        digits = digits[1:]
    if len(digits) < 10 or len(digits) > 11:
        return None
    if country_code == "7" and len(digits) != 10:
        return None
    return digits


def _as_decimal(value) -> Optional[str]:
    if value in (None, ""):
        return None
    quant = Decimal(str(value))
    normalized = quant.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return smart_str(text)


def _bool(value: Optional[bool]) -> Optional[str]:
    if value in (None, ""):
        return None
    return "true" if bool(value) else "false"


def _resolve_property_subtype(prop) -> Optional[str]:
    for attr in ("subtype", "house_type", "commercial_type", "land_type"):
        value = getattr(prop, attr, None)
        if value:
            return value
    return None


def _append_child(parent: Element, tag: str, text: Optional[str], always: bool = False) -> Optional[Element]:
    if text in (None, "") and not always:
        return None
    el = SubElement(parent, tag)
    if isinstance(text, bool):
        el.text = "true" if text else "false"
    elif text not in (None, ""):
        el.text = smart_str(text)
    return el


def _append_decimal(parent: Element, tag: str, value) -> Optional[Element]:
    text = _as_decimal(value)
    if text is None:
        return None
    return _append_child(parent, tag, text)


def _append_bool(parent: Element, tag: str, value) -> Optional[Element]:
    text = _bool(value)
    if text is None:
        return None
    return _append_child(parent, tag, text, always=True)


def _layout_photo_block(parent: Element, url: str, request=None) -> None:
    absolute = build_absolute_url(url, request=request)
    if not absolute or not _is_http_url(absolute):
        return
    lp = SubElement(parent, "LayoutPhoto")
    SubElement(lp, "FullUrl").text = absolute
    SubElement(lp, "IsDefault").text = "false"


def _object_tour_block(parent: Element, url: str, request=None) -> None:
    absolute = build_absolute_url(url, request=request)
    if not absolute or not _is_http_url(absolute):
        return
    tour = SubElement(parent, "ObjectTour")
    SubElement(tour, "FullUrl").text = absolute


def _build_description(prop, extra_lines: Sequence[str]) -> str:
    base = smart_str(getattr(prop, "description", "")).strip()
    extra = [smart_str(line).strip() for line in extra_lines if line]
    extra = [line for line in extra if line]
    if not extra:
        return base
    extras_text = "\n".join(extra)
    if base:
        return f"{base}\n\n{extras_text}"
    return extras_text


def _build_house_description(prop) -> Sequence[str]:
    lines = []
    mapping = {
        "wc_location": "Санузел",
        "sewerage_type": "Канализация",
        "water_supply_type": "Водоснабжение",
        "gas_supply_type": "Газ",
        "house_condition": "Состояние",
    }
    for field, label in mapping.items():
        value = getattr(prop, field, None)
        if value:
            display_method = getattr(prop, f"get_{field}_display", None)
            text = display_method() if callable(display_method) else smart_str(value)
            lines.append(f"{label}: {text}")

    bool_mapping = {
        "has_electricity": "Электричество",
        "has_garage": "Гараж",
        "has_pool": "Бассейн",
        "has_bathhouse": "Баня",
        "has_security": "Охрана",
    }
    for field, label in bool_mapping.items():
        if getattr(prop, field, None):
            lines.append(f"{label}: есть")

    return lines


@dataclass
class PhotoPayload:
    url: str
    is_default: bool


def _resolve_photo_url(photo, request=None) -> str:
    full_url_raw = getattr(photo, "full_url", None)
    if full_url_raw not in (None, ""):
        full_url = smart_str(full_url_raw).strip()
        if full_url:
            return full_url

    image = getattr(photo, "image", None)
    image_url = ""
    if image:
        try:
            image_url = smart_str(image.url)
        except Exception:
            image_url = ""
    if image_url:
        if _is_http_url(image_url):
            return image_url
        if request is not None:
            absolute = request.build_absolute_uri(image_url)
            if absolute and _is_http_url(absolute):
                return absolute
        absolute = build_absolute_url(image_url, request=request)
        if absolute and _is_http_url(absolute):
            return absolute

    return ""


def _collect_photos(prop, request=None) -> Sequence[PhotoPayload]:
    photos_qs = getattr(prop, "photos", None)
    if not photos_qs:
        return []

    queryset = photos_qs.all()

    ordering = []
    meta_ordering = getattr(getattr(queryset, "model", None), "_meta", None)
    if meta_ordering is not None and getattr(meta_ordering, "ordering", None):
        ordering = list(meta_ordering.ordering)

    if not ordering and hasattr(queryset.model, "sort"):
        ordering = ["-is_default", "sort", "id"]

    if not ordering:
        ordering = ["-is_default", "-id"]

    queryset = queryset.order_by(*ordering)

    result = []
    for photo in queryset:
        absolute = _resolve_photo_url(photo, request=request)
        if not absolute:
            continue
        result.append(
            PhotoPayload(
                url=absolute,
                is_default=bool(getattr(photo, "is_default", False)),
            )
        )
    return result


class CianFeedBuilder:
    def __init__(self, *, request=None):
        self.request = request

    def build(self, properties: Iterable) -> Element:
        root = Element("feed")
        SubElement(root, "feed_version").text = "2"
        for prop in properties:
            element = self._build_object(prop)
            if element is not None:
                root.append(element)
        return root

    def _build_object(self, prop) -> Optional[Element]:
        subtype_value = _resolve_property_subtype(prop)
        category_str = build_cian_category(
            getattr(prop, "category", None),
            getattr(prop, "operation", None),
            subtype_value,
        )
        if not category_str:
            return None

        obj = Element("object")
        _append_child(obj, "Category", category_str, always=True)
        external_id = getattr(prop, "external_id", "") or ""
        _append_child(obj, "ExternalId", external_id, always=True)

        extra_description_lines = []
        if getattr(prop, "category", None) == "house":
            extra_description_lines = list(_build_house_description(prop))

        description = _build_description(prop, extra_description_lines)
        _append_child(obj, "Description", description, always=bool(description))
        _append_child(obj, "Address", getattr(prop, "address", None))

        lat = getattr(prop, "lat", None)
        lng = getattr(prop, "lng", None)
        if lat not in (None, "") and lng not in (None, ""):
            coords = SubElement(obj, "Coordinates")
            _append_decimal(coords, "Lat", lat)
            _append_decimal(coords, "Lng", lng)

        _append_child(obj, "CadastralNumber", getattr(prop, "cadastral_number", None))

        self._append_phones(obj, prop)
        self._append_media(obj, prop)
        self._append_areas(obj, prop)
        self._append_deal_terms(obj, prop)
        self._append_category_specific(obj, prop)

        return obj

    def _append_phones(self, obj: Element, prop) -> None:
        country_raw = getattr(prop, "phone_country", None) or "7"
        country = _digits_only(country_raw) or "7"
        numbers = []
        for field in ("phone_number", "phone_number2"):
            normalized = _normalize_phone_number(getattr(prop, field, ""), country)
            if normalized and normalized not in numbers:
                numbers.append(normalized)

        if not numbers:
            return

        container = SubElement(obj, "Phones")
        for number in numbers:
            ph = SubElement(container, "PhoneSchema")
            _append_child(ph, "CountryCode", country, always=True)
            _append_child(ph, "Number", number, always=True)

    def _append_media(self, obj: Element, prop) -> None:
        layout_url = getattr(prop, "layout_photo_url", "")
        if layout_url:
            _layout_photo_block(obj, layout_url, request=self.request)

        tour_url = getattr(prop, "object_tour_url", "")
        if tour_url:
            _object_tour_block(obj, tour_url, request=self.request)

        photos = list(_collect_photos(prop, request=self.request))
        if not photos:
            return

        photos_el = SubElement(obj, "Photos")
        default_used = False
        for idx, payload in enumerate(photos):
            if not payload.url:
                continue

            mark_default = False
            if not default_used and payload.is_default:
                mark_default = True
            elif not default_used and idx == 0:
                mark_default = True

            for tag in ("Photo", "PhotoSchema"):
                photo_el = SubElement(photos_el, tag)
                SubElement(photo_el, "FullUrl").text = payload.url
                if mark_default:
                    SubElement(photo_el, "IsDefault").text = "true"

            if mark_default:
                default_used = True

    def _append_areas(self, obj: Element, prop) -> None:
        _append_decimal(obj, "TotalArea", getattr(prop, "total_area", None))
        _append_decimal(obj, "LivingArea", getattr(prop, "living_area", None))
        _append_decimal(obj, "KitchenArea", getattr(prop, "kitchen_area", None))
        _append_child(obj, "FloorNumber", getattr(prop, "floor_number", None))
        _append_child(obj, "Rooms", getattr(prop, "rooms", None))
        _append_child(obj, "FlatRoomsCount", getattr(prop, "flat_rooms_count", None))
        _append_child(obj, "LoggiasCount", getattr(prop, "loggias_count", None))
        _append_child(obj, "BalconiesCount", getattr(prop, "balconies_count", None))
        _append_child(obj, "WindowsViewType", getattr(prop, "windows_view_type", None))
        _append_child(obj, "SeparateWcsCount", getattr(prop, "separate_wcs_count", None))
        _append_child(obj, "CombinedWcsCount", getattr(prop, "combined_wcs_count", None))
        _append_child(obj, "RepairType", getattr(prop, "repair_type", None))

        if getattr(prop, "category", None) == "house":
            self._append_house_areas(obj, prop)

    def _append_house_areas(self, obj: Element, prop) -> None:
        land_area = getattr(prop, "land_area", None)
        unit = getattr(prop, "land_area_unit", "") or "sotka"
        if land_area not in (None, ""):
            value = Decimal(str(land_area))
            if unit == "sqm":
                value = value / Decimal("100")
                unit = "sotka"
            _append_decimal(obj, "LandArea", value)
            _append_child(obj, "LandAreaUnit", unit)
        _append_child(obj, "HouseFloorsCount", getattr(prop, "building_floors", None))
        material = getattr(prop, "building_material", None)
        if material:
            _append_child(obj, "HouseMaterialType", material)
        _append_child(obj, "YearBuild", getattr(prop, "building_build_year", None))

    def _append_deal_terms(self, obj: Element, prop) -> None:
        fields_present = [
            getattr(prop, "price", None),
            getattr(prop, "mortgage_allowed", None),
            getattr(prop, "agent_bonus_value", None),
            getattr(prop, "security_deposit", None),
            getattr(prop, "min_rent_term_months", None),
            getattr(prop, "sale_type", None),
        ]
        if not any(v not in (None, "") for v in fields_present):
            return

        bt = SubElement(obj, "BargainTerms")
        _append_decimal(bt, "Price", getattr(prop, "price", None))
        _append_child(bt, "Currency", getattr(prop, "currency", None) or "rur")
        _append_bool(bt, "MortgageAllowed", getattr(prop, "mortgage_allowed", None))

        sale_type = getattr(prop, "sale_type", "") or ""
        if sale_type:
            is_alternative = None
            if sale_type == "alternative":
                is_alternative = True
            elif sale_type == "free":
                is_alternative = False
            if is_alternative is not None:
                _append_bool(bt, "IsAlternative", is_alternative)

        agent_bonus_value = getattr(prop, "agent_bonus_value", None)
        if agent_bonus_value not in (None, ""):
            ab = SubElement(bt, "AgentBonus")
            _append_decimal(ab, "Value", agent_bonus_value)
            is_percent = bool(getattr(prop, "agent_bonus_is_percent", False))
            _append_child(ab, "PaymentType", "percent" if is_percent else "fixed", always=True)
            if not is_percent:
                _append_child(ab, "Currency", getattr(prop, "currency", None) or "rur")

        _append_decimal(bt, "SecurityDeposit", getattr(prop, "security_deposit", None))
        _append_child(bt, "MinRentTerm", getattr(prop, "min_rent_term_months", None))

    def _append_category_specific(self, obj: Element, prop) -> None:
        category = getattr(prop, "category", None)
        if category == "flat":
            self._append_flat_specific(obj, prop)
        elif category == "house":
            self._append_house_specific(obj, prop)
        elif category == "commercial":
            self._append_commercial_specific(obj, prop)

        _append_child(obj, "IsEuroFlat", True if getattr(prop, "is_euro_flat", False) else None)
        _append_child(obj, "IsApartments", True if getattr(prop, "is_apartments", False) else None)
        _append_child(obj, "IsPenthouse", True if getattr(prop, "is_penthouse", False) else None)

        self._append_building_info(obj, prop)

        for name in [
            "has_internet",
            "has_furniture",
            "has_kitchen_furniture",
            "has_tv",
            "has_washer",
            "has_conditioner",
            "has_refrigerator",
            "has_dishwasher",
            "has_shower",
            "has_phone",
            "has_ramp",
            "has_bathtub",
        ]:
            if getattr(prop, name, None):
                tag = "".join(part.capitalize() for part in name.split("_"))
                _append_child(obj, tag, "true", always=True)

    def _append_flat_specific(self, obj: Element, prop) -> None:
        room_type = getattr(prop, "room_type", None) or ""
        layout_map = {
            "combined": "combined",
            "both": "both",
            "separate": "separate",
        }
        if room_type:
            mapped = layout_map.get(room_type.lower())
            if mapped:
                _append_child(obj, "RoomType", mapped)

    def _append_house_specific(self, obj: Element, prop) -> None:
        self._append_house_utilities(obj, prop)
        self._append_house_land(obj, prop)
        _append_child(obj, "HeatingType", getattr(prop, "heating_type", None))

    def _append_house_utilities(self, obj: Element, prop) -> None:
        gas_value = HOUSE_GAS_MAP.get((getattr(prop, "gas_supply_type", "") or "").strip())
        if gas_value:
            gas = SubElement(obj, "Gas")
            SubElement(gas, "Type").text = gas_value

        drainage_value = HOUSE_DRAINAGE_MAP.get((getattr(prop, "sewerage_type", "") or "").strip())
        if drainage_value:
            drainage = SubElement(obj, "Drainage")
            SubElement(drainage, "Type").text = drainage_value

        water_value = HOUSE_WATER_MAP.get((getattr(prop, "water_supply_type", "") or "").strip())
        if water_value:
            water = SubElement(obj, "Water")
            SubElement(water, "SuburbanWaterType").text = water_value

    def _append_house_land(self, obj: Element, prop) -> None:
        area_text = _as_decimal(getattr(prop, "land_area", None))
        unit_value = smart_str(getattr(prop, "land_area_unit", "")).strip()
        permitted = smart_str(getattr(prop, "permitted_land_use", "")).strip()
        land_category = smart_str(getattr(prop, "land_category", "")).strip()
        has_contract = getattr(prop, "is_land_with_contract", None)

        land_element = None

        if area_text and unit_value:
            land_element = SubElement(obj, "Land")
            _append_child(land_element, "Area", area_text, always=True)
            _append_child(land_element, "AreaUnitType", unit_value, always=True)
        elif any([permitted, land_category, has_contract in (True, False)]):
            land_element = SubElement(obj, "Land")

        if land_element is None:
            return

        if has_contract in (True, False):
            _append_bool(land_element, "IsLandWithContract", has_contract)

        if permitted:
            _append_child(land_element, "PermittedLandUse", permitted)

        if land_category:
            _append_child(land_element, "LandCategory", land_category)

    def _append_commercial_specific(self, obj: Element, prop) -> None:
        _append_decimal(obj, "Power", getattr(prop, "power", None))
        _append_child(obj, "ParkingPlacesCount", getattr(prop, "parking_places", None))
        if getattr(prop, "has_parking", None):
            _append_child(obj, "HasParking", "true", always=True)

        if getattr(prop, "is_rent_by_parts", False):
            _append_child(obj, "IsRentByParts", "true", always=True)
            _append_child(obj, "RentByPartsDescription", getattr(prop, "rent_by_parts_desc", None))

    def _append_building_info(self, obj: Element, prop) -> None:
        _append_child(obj, "FloorsCount", getattr(prop, "building_floors", None))
        _append_child(obj, "BuildYear", getattr(prop, "building_build_year", None))
        if getattr(prop, "building_material", None):
            _append_child(obj, "MaterialType", getattr(prop, "building_material", None))
        ceiling = getattr(prop, "building_ceiling_height", None) or getattr(prop, "ceiling_height", None)
        _append_decimal(obj, "CeilingHeight", ceiling)
        _append_child(obj, "PassengerLiftsCount", getattr(prop, "building_passenger_lifts", None))
        _append_child(obj, "CargoLiftsCount", getattr(prop, "building_cargo_lifts", None))


__all__ = [
    "build_cian_category",
    "build_absolute_url",
    "CianFeedBuilder",
    "_resolve_property_subtype",
    "build_cian_feed_xml",
]


def build_cian_feed_xml(properties: Iterable, *, request=None) -> bytes:
    builder = CianFeedBuilder(request=request)
    root = builder.build(properties)
    return tostring(root, encoding="utf-8", xml_declaration=True)
