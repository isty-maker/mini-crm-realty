from core.cian import load_registry
from core.forms import PropertyForm


EXCLUDED = {
    "jk_id", "jk_name", "house_id", "house_name", "section_number",
    "undergrounds", "metro", "object_tour_url", "furnishing_details",
}


def test_every_feed_related_field_has_mapping_somewhere():
    reg = load_registry()
    common = reg.get("common", {}).get("fields", {})
    categories = reg.get("categories", {})
    deal_terms = reg.get("deal_terms", {}).get("fields", {})

    mapped = set(common.keys()) | set(deal_terms.keys())
    for cat in categories.values():
        mapped |= set(cat.get("fields", {}).keys())

    photos = reg.get("common", {}).get("photos", {})
    if "layout_full_url" in photos:
        mapped.add("layout_photo_url")

    missing = [
        f for f in PropertyForm.FEED_RELATED_FIELDS
        if f not in EXCLUDED and f not in mapped
    ]
    assert not missing, f"Unmapped form fields: {sorted(missing)}"
