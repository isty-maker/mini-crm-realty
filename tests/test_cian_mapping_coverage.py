from core.forms import PropertyForm
from core.cian import load_registry

EXCLUDED_FIELDS = {
    "jk_id",
    "jk_name",
    "house_id",
    "house_name",
    "section_number",
    "undergrounds",
    "metro",
}


def _collect_mapped_fields() -> set[str]:
    registry = load_registry()
    mapped = set(registry.get("common", {}).get("fields", {}).keys())

    deal_terms = registry.get("deal_terms", {}).get("fields", {})
    mapped.update(deal_terms.keys())

    for category in registry.get("categories", {}).values():
        mapped.update(category.get("fields", {}).keys())

    photos = registry.get("common", {}).get("photos", {})
    if "layout_full_url" in photos:
        mapped.add("layout_photo_url")

    return mapped


def test_every_form_field_is_mapped_somewhere():
    mapped_fields = _collect_mapped_fields()
    unmapped = [
        field for field in PropertyForm.FEED_RELATED_FIELDS
        if field not in EXCLUDED_FIELDS and field not in mapped_fields
    ]
    assert not unmapped, f"Unmapped form fields: {sorted(unmapped)}"


def test_deal_terms_have_price_and_currency():
    registry = load_registry()
    deal_terms = registry.get("deal_terms", {}).get("fields", {})
    missing = [name for name in ("price", "currency") if name not in deal_terms]
    assert not missing, f"Deal terms missing: {missing}"
