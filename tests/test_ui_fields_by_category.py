import pytest

from core.forms import fields_for_category, UI_EXCLUDE


@pytest.mark.parametrize(
    "category, operation",
    [
        ("house", "sale"),
        ("flat", "sale"),
        ("flat", "rent_long"),
        ("room", "sale"),
    ],
)
def test_each_category_has_nonempty_fieldset(category, operation):
    fields = fields_for_category(category, operation)
    assert fields, f"No fields returned for {category}/{operation}"


def test_excludes_jk_undergrounds_service():
    fields = fields_for_category("flat", "sale")
    assert not (UI_EXCLUDE & set(fields))
