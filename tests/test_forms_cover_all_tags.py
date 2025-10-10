from core.cian import load_registry
from core.forms import FORMS_EXCLUDE, PropertyForm


def test_form_has_field_for_every_exported_tag():
    registry = load_registry()

    required = set(registry.get("common", {}).get("fields", {}).keys())
    required |= set(registry.get("deal_terms", {}).get("fields", {}).keys())

    categories = registry.get("categories", {}) or {}
    for config in categories.values():
        required |= set((config.get("fields") or {}).keys())

    required |= {"phone_country", "phone_number", "phone_number2"}

    missing = [
        field_name
        for field_name in sorted(required)
        if field_name not in FORMS_EXCLUDE
        and field_name not in PropertyForm.FEED_RELATED_FIELDS
    ]

    assert not missing, f"В форме отсутствуют поля под теги: {missing}"
