from core.cian import load_registry
from core.forms import PropertyForm


EXCLUDED = {
    "jk_id",
    "jk_name",
    "house_id",
    "house_name",
    "section_number",
    "undergrounds",
    "metro",
    "object_tour_url",
    "furnishing_details",
    "layout_photo_url",
}


def test_every_feed_related_field_has_mapping_somewhere():
    reg = load_registry()
    common = reg.get("common", {}).get("fields", {})
    categories = reg.get("categories", {})
    deal_terms = reg.get("deal_terms", {}).get("fields", {})

    mapped = set(common.keys()) | set(deal_terms.keys())
    for cat in categories.values():
        mapped |= set(cat.get("fields", {}).keys())

    missing = [
        field
        for field in PropertyForm.FEED_RELATED_FIELDS
        if field not in EXCLUDED and field not in mapped
    ]

    assert not missing, f"Unmapped form fields: {sorted(missing)}"
