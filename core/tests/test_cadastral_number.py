from decimal import Decimal
from xml.etree.ElementTree import tostring

import pytest

from core.cian import build_ad_xml
from core.models import Photo, Property


@pytest.mark.django_db
def test_cadastral_number_is_exported_when_filled():
    prop = Property.objects.create(
        category="flat",
        operation="sale",
        external_id="CAD-001",
        address="Москва",
        total_area=Decimal("45"),
        floor_number=6,
        price=Decimal("5000000"),
        currency="rur",
        cadastral_number="77:01:0004015:345",
        phone_number="+7 999 000-00-00",
    )
    Photo.objects.create(
        property=prop,
        full_url="http://example.com/p.jpg",
        is_default=True,
    )

    result = build_ad_xml(prop)
    xml = tostring(result.element, encoding="unicode")

    assert "<CadastralNumber>77:01:0004015:345</CadastralNumber>" in xml
