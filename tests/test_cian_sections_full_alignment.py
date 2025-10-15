from decimal import Decimal
from xml.etree.ElementTree import fromstring

import pytest

from core.cian import build_cian_feed
from core.models import Photo, Property


def _first_object_xml(prop: Property):
    feed = build_cian_feed([prop])
    root = fromstring(feed.xml)
    return root.find("object")


@pytest.mark.django_db
def test_house_sale_utilities_and_condition():
    prop = Property.objects.create(
        category="house",
        operation="sale",
        address="МО",
        total_area=Decimal("120"),
        land_area=Decimal("6.0"),
        land_area_unit="sotka",
        has_electricity=True,
        has_gas=True,
        has_water=True,
        has_drainage=True,
        gas_supply_type="main_on_plot",
        water_supply_type="borehole",
        sewerage_type="septic",
        house_condition="ready",
        wc_location="inside",
        heating_type="centralGas",
        price=Decimal("10000000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(
        property=prop,
        full_url="http://example.com/house.jpg",
        is_default=True,
    )

    obj = _first_object_xml(prop)

    assert obj is not None
    assert obj.findtext("HasElectricity") == "true"
    assert obj.findtext("HasGas") == "true"
    assert obj.findtext("HasWater") == "true"
    assert obj.findtext("HasDrainage") == "true"

    gas = obj.find("Gas")
    assert gas is not None
    assert gas.findtext("Type") == "main"

    water = obj.find("Water")
    assert water is not None
    assert water.findtext("SuburbanWaterType") == "borehole"

    drainage = obj.find("Drainage")
    assert drainage is not None
    assert drainage.findtext("Type") == "septicTank"

    assert obj.findtext("Condition") == "ready"
    assert obj.findtext("HeatingType") == "centralGas"
    assert obj.findtext("WcLocationType") == "inside"


@pytest.mark.django_db
def test_flat_sale_building_and_euro_layout():
    prop = Property.objects.create(
        category="flat",
        operation="sale",
        address="СПб",
        total_area=Decimal("55"),
        living_area=Decimal("30"),
        kitchen_area=Decimal("10"),
        floor_number=9,
        flat_rooms_count=2,
        is_euro_flat=True,
        building_floors=16,
        building_build_year=2008,
        building_material="brick",
        building_ceiling_height=Decimal("2.70"),
        building_passenger_lifts=2,
        building_cargo_lifts=1,
        price=Decimal("7500000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(
        property=prop,
        full_url="http://example.com/flat.jpg",
        is_default=True,
    )

    obj = _first_object_xml(prop)

    assert obj is not None
    assert obj.findtext("Category") == "flatSale"
    assert obj.findtext("IsEuroFlat") == "true"

    building = obj.find("Building")
    assert building is not None
    assert building.findtext("FloorsCount") == "16"
    assert building.findtext("BuildYear") == "2008"
    assert building.findtext("MaterialType") == "brick"
    assert building.findtext("CeilingHeight") == "2.7"
    assert building.findtext("PassengerLiftsCount") == "2"
    assert building.findtext("CargoLiftsCount") == "1"


@pytest.mark.django_db
def test_flat_rent_beds_and_deal_terms():
    prop = Property.objects.create(
        category="flat",
        operation="rent_long",
        address="Москва",
        total_area=Decimal("33.5"),
        floor_number=7,
        flat_rooms_count=2,
        beds_count=3,
        lease_term_type="longTerm",
        prepay_months=1,
        deposit=Decimal("55000"),
        price=Decimal("55000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(
        property=prop,
        full_url="http://example.com/rent.jpg",
        is_default=True,
    )

    obj = _first_object_xml(prop)

    assert obj is not None
    assert obj.findtext("Category") == "flatRent"
    assert obj.findtext("BedsCount") == "3"

    bargain = obj.find("BargainTerms")
    assert bargain is not None
    assert bargain.findtext("LeaseTermType") == "longTerm"
    assert bargain.findtext("PrepayMonths") == "1"
    assert bargain.findtext("Deposit") == "55000"


@pytest.mark.django_db
def test_room_sale_room_area_and_count():
    prop = Property.objects.create(
        category="room",
        operation="sale",
        address="Казань",
        total_area=Decimal("12.0"),
        rooms_for_sale_count=1,
        floor_number=5,
        price=Decimal("1500000"),
        currency="rur",
        export_to_cian=True,
    )
    Photo.objects.create(
        property=prop,
        full_url="http://example.com/room.jpg",
        is_default=True,
    )

    obj = _first_object_xml(prop)

    assert obj is not None
    assert obj.findtext("Category") == "roomSale"
    assert obj.findtext("RoomArea") == "12"
    assert obj.findtext("RoomsForSaleCount") == "1"
    assert obj.findtext("FloorNumber") == "5"
