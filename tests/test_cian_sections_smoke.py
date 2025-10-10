from decimal import Decimal
from xml.etree.ElementTree import fromstring

import pytest

from core.cian import build_cian_feed
from core.models import Photo, Property


def _export_xml(objects):
    feed = build_cian_feed(objects)
    return fromstring(feed.xml)


@pytest.mark.django_db
def test_flat_sale_has_critical_tags():
    prop = Property.objects.create(
        category="flat",
        operation="sale",
        address="Москва",
        total_area=Decimal("45"),
        floor_number=6,
        flat_rooms_count=2,
        windows_view_type="yard",
        price=Decimal("5000000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(property=prop, full_url="http://example.com/p.jpg")

    root = _export_xml([prop])
    obj = root.find("object")
    assert obj is not None
    assert obj.findtext("Category") == "flatSale"
    assert obj.findtext("FlatRoomsCount") == "2"
    assert obj.findtext("WindowsViewType") == "yard"
    assert obj.findtext("BargainTerms/Price") == "5000000"


@pytest.mark.django_db
def test_house_sale_has_land_and_wc():
    prop = Property.objects.create(
        category="house",
        operation="sale",
        address="Тюмень",
        total_area=Decimal("90"),
        land_area=Decimal("6.5"),
        land_area_unit="sotka",
        wc_location="inside",
        price=Decimal("6500000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(property=prop, full_url="http://example.com/h.jpg")

    root = _export_xml([prop])
    obj = root.find("object")
    assert obj is not None
    land = obj.find("Land")
    assert land is not None
    assert land.findtext("Area") == "6.5"
    assert land.findtext("AreaUnitType") == "sotka"
    assert obj.findtext("WcLocationType") == "inside"


@pytest.mark.django_db
def test_flat_rent_includes_bargain_terms():
    prop = Property.objects.create(
        category="flat",
        operation="rent_long",
        address="СПб",
        total_area=Decimal("33.5"),
        floor_number=7,
        flat_rooms_count=2,
        beds_count=3,
        lease_term_type="longTerm",
        prepay_months=1,
        deposit=Decimal("55000"),
        utilities_terms="included",
        price=Decimal("55000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(property=prop, full_url="http://example.com/r.jpg")

    root = _export_xml([prop])
    obj = root.find("object")
    assert obj is not None
    assert obj.findtext("Category") == "flatRent"
    terms = obj.find("BargainTerms")
    assert terms is not None
    assert terms.findtext("LeaseTermType") == "longTerm"
    assert terms.findtext("PrepayMonths") == "1"
    assert terms.findtext("Deposit") == "55000"
    assert obj.findtext("BedsCount") == "3"


@pytest.mark.django_db
def test_room_sale_uses_room_area():
    prop = Property.objects.create(
        category="room",
        operation="sale",
        address="Казань",
        total_area=Decimal("12.0"),
        rooms_for_sale_count=1,
        price=Decimal("1500000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(property=prop, full_url="http://example.com/rm.jpg")

    root = _export_xml([prop])
    obj = root.find("object")
    assert obj is not None
    assert obj.findtext("RoomArea") == "12"
    assert obj.findtext("RoomsForSaleCount") == "1"
