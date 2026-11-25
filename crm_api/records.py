"""The v1 allowlist, serialisation and validation of property changes."""



from core.forms import PropertyForm
from core.models import Property
from core.private_records import SCOPES, model_values, prepare_record, record_version
from core.property_detail import PropertySectionForm, Section
from core.property_writes import current_values, property_version
from core.workspace_models import PropertyDocumentType, PropertyWorkspace

from .access import APIError


WORKSPACE = ("status", "terms", "legal")
COLLECTIONS = ("files", "documents", "bases", "owners", "notes")
LISTING_FIELDS = (
    "address", "category", "operation", "flat_type", "room_type_ext", "house_type", "commercial_type", "land_type",
    "title", "description", "price", "currency", "total_area", "living_area", "kitchen_area", "flat_rooms_count",
    "rooms", "room_area", "rooms_for_sale_count", "floor_number", "building_floors", "building_build_year",
    "building_material", "building_ceiling_height", "ceiling_height", "room_type", "separate_wcs_count",
    "combined_wcs_count", "balconies_count", "loggias_count", "repair_type", "land_area", "land_area_unit",
    "layout_photo_url", "sale_type", "mortgage_allowed", "bargain_allowed", "bargain_conditions", "furnishing_details",
    "bedrooms_count", "house_condition", "heating_type", "wc_location", "sewerage_type", "water_supply_type",
    "gas_supply_type", "power", "parking_places", "jk_name", "permitted_land_use", "land_category",
)
CREATE_ONLY = {"category", "operation", "flat_type", "room_type_ext", "house_type", "commercial_type", "land_type"}
READ_FIELDS = (*LISTING_FIELDS, "status", "is_archived", "export_to_cian", "export_to_domklik", "updated_at")


def ensure_fields(model, names, data):
    if not isinstance(data, dict):
        raise APIError(422, "invalid_fields", "Expected an object.")
    invalid = set(data) - set(names)
    if invalid:
        raise APIError(422, "invalid_fields", "Fields are outside the allowlist.", fields=sorted(invalid))
    errors = {}
    for name, value in data.items():
        field = model._meta.get_field(name)
        field_type = field.get_internal_type()
        if value is None:
            valid = field.null
        elif field_type in {"IntegerField", "PositiveIntegerField", "PositiveSmallIntegerField",
                            "BigIntegerField", "PositiveBigIntegerField", "ForeignKey"}:
            valid = type(value) is int
        elif field_type == "BooleanField":
            valid = type(value) is bool
        else:
            valid = isinstance(value, str)  # Includes decimals and ISO dates.
        if not valid:
            errors[name] = "Invalid JSON type or null is not allowed."
    if errors:
        raise APIError(422, "invalid_fields", "Invalid values.", fields=errors)
    return data


def serialize_record(prop, scope, row):
    data = {"id": row.pk, "version": record_version(prop, scope, row),
            **model_values(row, SCOPES[scope].fields)}
    if scope == "notes":
        data.update(author_id=row.author_id, created_at=row.created_at, updated_at=row.updated_at)
    if scope == "status":
        data.update(status_changed_by=row.status_changed_by_id, status_changed_at=row.status_changed_at)
    return data


def aggregate(prop):
    workspace = PropertyWorkspace.objects.filter(property=prop).first() or PropertyWorkspace(property=prop)
    work = {scope: serialize_record(prop, scope, workspace) for scope in WORKSPACE}
    collections = {
        scope: [serialize_record(prop, scope, row) for row in
                SCOPES[scope].model.objects.filter(workspace_id=workspace.pk).order_by("pk")]
        if workspace.pk else [] for scope in COLLECTIONS
    }
    versions = [entry["version"] for entry in work.values()]
    versions.extend(entry["version"] for entries in collections.values() for entry in entries)
    version = property_version(prop, "api:" + ":".join(versions), READ_FIELDS)
    return {"id": prop.pk, "version": version, "listing": current_values(prop, READ_FIELDS),
            "workspace": work, "collections": collections}


def checked_record(prop, scope, row, data, expected):
    fields = SCOPES[scope].fields
    ensure_fields(SCOPES[scope].model, fields, data)
    before = model_values(row, fields)
    form, version, changes = prepare_record(prop, scope, row, data)
    if expected is not None and expected != version:
        raise APIError(409, "conflict", "Record changed.", version=version, current=before)
    if not form.is_valid():
        raise APIError(422, "validation", "Record is invalid.", fields=form.errors.get_json_data(),
                       version=version, old=before, proposed=data)
    return version, changes, {name: {"old": before[name], "new": value} for name, value in changes.items()}


def checked_listing(prop, data, version):
    names = set(LISTING_FIELDS) - CREATE_ONLY
    ensure_fields(Property, names, data)
    if not data:
        return {}
    form = PropertySectionForm(prop, Section("api", "Listing", tuple(sorted(data))), data)
    if not form.is_valid():
        raise APIError(422, "validation", "Listing is invalid.", fields=form.errors.get_json_data(), version=version,
                       old=current_values(prop, data), proposed=data)
    return form.changed_values()


def create_listing(data):
    ensure_fields(Property, LISTING_FIELDS, data)
    form = PropertyForm({**data, "status": "draft", "export_to_cian": False,
                         "export_to_domklik": False, "is_archived": False})
    if not form.is_valid():
        raise APIError(422, "validation", "Listing is invalid.", fields=form.errors.get_json_data())
    prop = form.save(commit=False)
    if not prop.address.strip():
        raise APIError(422, "validation", "An address is required.", fields={"address": "Required"})
    prop.status = "draft"
    prop.export_to_cian = prop.export_to_domklik = prop.is_archived = False
    return prop


def document_types():
    return list(PropertyDocumentType.objects.order_by("slug").values("id", "slug", "title"))
