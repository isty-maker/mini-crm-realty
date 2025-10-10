from decimal import Decimal
from xml.etree.ElementTree import tostring

import pytest

from core.cian import build_ad_xml, resolve_category
from core.models import Photo, Property


@pytest.mark.django_db
def test_full_coverage_flat_house_land_commercial_garage():
    flat = Property.objects.create(
        category="flat",
        operation="sale",
        external_id="FLAT-001",
        description="Уютная квартира",
        address="Москва",
        lat=Decimal("55.751"),
        lng=Decimal("37.618"),
        price=Decimal("12500000"),
        currency="usd",
        mortgage_allowed=True,
        agent_bonus_value=Decimal("100000"),
        agent_bonus_is_percent=True,
        security_deposit=Decimal("25000"),
        min_rent_term_months=12,
        phone_country="7",
        phone_number="9991234567",
        layout_photo_url="/media/layouts/flat.jpg",
        total_area=Decimal("48.5"),
        living_area=Decimal("30.2"),
        kitchen_area=Decimal("10.3"),
        floor_number=7,
        rooms=2,
        flat_rooms_count=2,
        room_type="separate",
        windows_view_type="street",
        separate_wcs_count=1,
        combined_wcs_count=1,
        repair_type="euro",
        is_euro_flat=True,
        is_apartments=True,
        loggias_count=1,
        balconies_count=1,
    )
    Photo.objects.create(property=flat, full_url="https://example.com/flat-main.jpg", is_default=True)
    Photo.objects.create(property=flat, full_url="/media/photos/flat-2.jpg", sort=20)

    house = Property.objects.create(
        category="house",
        operation="sale",
        external_id="HOUSE-001",
        description="Дом с участком",
        address="Зеленоград",
        lat=Decimal("56.01"),
        lng=Decimal("37.21"),
        price=Decimal("18500000"),
        currency="rur",
        phone_country="7",
        phone_number="9997654321",
        total_area=Decimal("180.0"),
        building_floors=2,
        building_build_year=2012,
        building_material="brick",
        bedrooms_count=4,
        wc_location="inside",
        heating_type="gas",
        ceiling_height=Decimal("3.2"),
        house_condition="ready",
        has_garage=True,
        land_area=Decimal("8.5"),
        land_area_unit="sotka",
        permitted_land_use="individualHousingConstruction",
        is_land_with_contract=True,
        land_category="settlements",
        gas_supply_type="gasholder",
        sewerage_type="septic",
        water_supply_type="borehole",
        has_electricity=True,
        power=15,
        has_terrace=True,
        has_cellar=True,
        has_pool=True,
        has_bathhouse=True,
        has_security=True,
    )
    Photo.objects.create(property=house, full_url="https://example.com/house-main.jpg", is_default=True)

    land = Property.objects.create(
        category="land",
        operation="sale",
        external_id="LAND-001",
        description="Участок",
        address="Дмитров",
        price=Decimal("4500000"),
        currency="rur",
        phone_country="7",
        phone_number="9995544332",
        land_area=Decimal("12.4"),
        land_area_unit="sotka",
        permitted_land_use="gardening",
        land_category="settlements",
        has_electricity=True,
        power=10,
        is_land_with_contract=True,
    )

    commercial = Property.objects.create(
        category="commercial",
        operation="sale",
        external_id="COMM-001",
        description="Офис",
        address="Москва",
        price=Decimal("9800000"),
        currency="eur",
        phone_country="7",
        phone_number="9991100110",
        commercial_type="office",
        total_area=Decimal("82.0"),
        ceiling_height=Decimal("3.5"),
        is_rent_by_parts=True,
        rent_by_parts_desc="Можно делить на 2 блока",
        has_parking=True,
        parking_places=4,
        power=20,
        has_ramp=True,
    )

    garage = Property.objects.create(
        category="garage",
        operation="sale",
        external_id="GAR-001",
        description="Гараж",
        address="Химки",
        price=Decimal("750000"),
        currency="rur",
        phone_country="7",
        phone_number="9887766554",
        total_area=Decimal("18.0"),
        has_electricity=True,
        power=5,
    )

    results = [
        build_ad_xml(obj)
        for obj in (flat, house, land, commercial, garage)
    ]

    for result in results:
        assert result.uncovered_fields == set()
        xml_text = tostring(result.element, encoding="unicode")
        assert "<Category>" in xml_text

    flat_xml = tostring(results[0].element, encoding="unicode")
    assert "<RoomsCount>2</RoomsCount>" in flat_xml
    assert "<RoomType>separate</RoomType>" in flat_xml
    assert "<IsApartments>true</IsApartments>" in flat_xml

    house_xml = tostring(results[1].element, encoding="unicode")
    assert "<Gas><Type>gasHolder</Type></Gas>" in house_xml
    assert "<Land><Area>8.5</Area>" in house_xml
    assert "<Electricity><Available>true</Available><Power>15</Power></Electricity>" in house_xml

    land_xml = tostring(results[2].element, encoding="unicode")
    assert "<Area>12.4</Area>" in land_xml
    assert "<Electricity><Available>true</Available><Power>10</Power></Electricity>" in land_xml

    commercial_xml = tostring(results[3].element, encoding="unicode")
    assert "<IsRentByParts>true</IsRentByParts>" in commercial_xml
    assert "<BargainTerms><Price>9800000" in commercial_xml

    garage_xml = tostring(results[4].element, encoding="unicode")
    assert "<Electricity><Available>true</Available><Power>5</Power></Electricity>" in garage_xml


@pytest.mark.django_db
def test_values_normalized():
    prop = Property.objects.create(
        category="house",
        operation="sale",
        external_id="VAL-001",
        description="Значения",
        address="Коломна",
        price=Decimal("123456.70"),
        currency="eur",
        mortgage_allowed=True,
        agent_bonus_value=Decimal("12.50"),
        agent_bonus_is_percent=True,
        phone_country="7",
        phone_number="9001234567",
        total_area=Decimal("99.9"),
        gas_supply_type="gasholder",
        sewerage_type="cesspool",
        water_supply_type="well",
        land_area=Decimal("6.0"),
        land_area_unit="sqm",
        permitted_land_use="individualHousingConstruction",
        land_category="settlements",
        has_electricity=True,
        power=7,
    )

    result = build_ad_xml(prop)
    xml_text = tostring(result.element, encoding="unicode")

    assert "<Currency>EUR</Currency>" in xml_text
    assert "<MortgageAllowed>true</MortgageAllowed>" in xml_text
    assert "<Value>12.5</Value>" in xml_text
    assert "<PaymentType>percent</PaymentType>" in xml_text
    assert "<Gas><Type>gasHolder</Type></Gas>" in xml_text
    assert "<Drainage><Type>cesspool</Type></Drainage>" in xml_text
    assert "<Water><SuburbanWaterType>well</SuburbanWaterType></Water>" in xml_text
    assert "<Land><Area>6</Area><AreaUnitType>sqm" in xml_text


@pytest.mark.django_db
def test_no_empty_tags():
    prop = Property.objects.create(
        category="flat",
        operation="sale",
        external_id="EMPTY-001",
        description="Только обязательное",
        address="Москва",
        price=Decimal("5000000"),
        currency="rur",
        phone_country="7",
        total_area=Decimal("40.0"),
    )

    result = build_ad_xml(prop)
    xml_text = tostring(result.element, encoding="unicode")

    assert "Phones" not in xml_text
    assert "AgentBonus" not in xml_text
    assert "LayoutPhoto" not in xml_text
    assert "<BargainTerms><Price>5000000</Price><Currency>RUR" in xml_text

    assert resolve_category(prop) == "flatSale"
