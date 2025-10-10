from decimal import Decimal
from xml.etree.ElementTree import fromstring

import pytest

from core.cian import build_cian_feed
from core.models import Photo, Property


@pytest.mark.django_db
def test_flat_sale_building_and_euro_layout():
    prop = Property.objects.create(
        category="flat",
        operation="sale",
        address="СПб",
        total_area=Decimal("55"),
        floor_number=9,
        flat_rooms_count=2,
        is_euro_flat=True,
        building_floors=16,
        building_build_year=2008,
        building_material="brick",
        building_ceiling_height=Decimal("2.7"),
        building_passenger_lifts=2,
        building_cargo_lifts=1,
        price=Decimal("7500000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(
        property=prop,
        full_url="https://example.com/flat.jpg",
        is_default=True,
    )

    feed = build_cian_feed([prop])
    root = fromstring(feed.xml)
    obj = root.find("object")
    assert obj is not None
    building = obj.find("Building")
    assert building is not None
    assert obj.findtext("IsEuroFlat") == "true"
    assert building.findtext("FloorsCount") == "16"
    assert building.findtext("BuildYear") == "2008"
    assert building.findtext("MaterialType") == "brick"
    assert building.findtext("CeilingHeight") == "2.7"
    assert building.findtext("PassengerLiftsCount") == "2"
    assert building.findtext("CargoLiftsCount") == "1"
