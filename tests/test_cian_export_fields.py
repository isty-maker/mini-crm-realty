from __future__ import annotations

from decimal import Decimal
from xml.etree import ElementTree as ET

from django.test import TestCase
from django.urls import reverse

from core.cian import build_cian_feed
from core.models import Photo, Property


def _export_feed(client) -> ET.Element:
    response = client.get(reverse("export_cian"))
    assert response.status_code == 200
    return ET.fromstring(response.content)


def _find_object(root: ET.Element, external_id: str) -> ET.Element:
    for obj in root.findall("object"):
        if obj.findtext("ExternalId") == external_id:
            return obj
    raise AssertionError(f"object with ExternalId={external_id} not found")


class TestCianMapping(TestCase):
    def _create_photo(self, prop: Property) -> None:
        Photo.objects.create(
            property=prop,
            full_url="https://example.com/photo.jpg",
            is_default=True,
        )

    def test_flat_building_block_present(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            external_id="FLAT-BUILDING",
            address="Москва",
            total_area=Decimal("45.6"),
            floor_number=5,
            rooms=2,
            price=Decimal("9600000"),
            phone_number="+7 999 111-22-33",
            building_floors=17,
            building_build_year=2015,
            building_material="brick",
            building_ceiling_height=Decimal("2.80"),
            export_to_cian=True,
        )
        self._create_photo(prop)

        root = _export_feed(self.client)
        obj = _find_object(root, "FLAT-BUILDING")

        building = obj.find("Building")
        self.assertIsNotNone(building, "Building block must be present for flats")
        self.assertEqual(building.findtext("FloorsCount"), "17")
        self.assertEqual(building.findtext("BuildYear"), "2015")
        self.assertEqual(building.findtext("MaterialType"), "brick")
        self.assertEqual(building.findtext("CeilingHeight"), "2.8")

    def test_house_utilities_present(self):
        prop = Property.objects.create(
            category="house",
            operation="sale",
            external_id="HOUSE-UTIL",
            address="Зеленоград",
            total_area=Decimal("120"),
            land_area=Decimal("10"),
            land_area_unit="sotka",
            price=Decimal("12500000"),
            phone_number="+7 900 000-00-00",
            gas_supply_type="main_on_plot",
            sewerage_type="septic",
            water_supply_type="borehole",
            has_electricity=True,
            power=15,
            export_to_cian=True,
        )
        self._create_photo(prop)

        root = _export_feed(self.client)
        obj = _find_object(root, "HOUSE-UTIL")

        gas = obj.find("Gas")
        self.assertIsNotNone(gas)
        self.assertEqual(gas.findtext("Type"), "main")

        drainage = obj.find("Drainage")
        self.assertIsNotNone(drainage)
        self.assertEqual(drainage.findtext("Type"), "septicTank")

        water = obj.find("Water")
        self.assertIsNotNone(water)
        self.assertEqual(water.findtext("SuburbanWaterType"), "borehole")

        self.assertEqual(obj.findtext("HasElectricity"), "true")

        electricity = obj.find("Electricity")
        self.assertIsNotNone(electricity)
        self.assertEqual(electricity.findtext("Power"), "15")

    def test_full_coverage_no_skips(self):
        flat = Property.objects.create(
            category="flat",
            operation="sale",
            external_id="FLAT-COVER",
            address="Москва",
            total_area=Decimal("55.4"),
            living_area=Decimal("30"),
            kitchen_area=Decimal("12"),
            floor_number=8,
            rooms=2,
            price=Decimal("11250000"),
            currency="rur",
            phone_number="+7 901 123-45-67",
            loggias_count=1,
            balconies_count=1,
            repair_type="euro",
            is_apartments=True,
            building_floors=22,
            building_build_year=2018,
            building_material="monolith",
            building_ceiling_height=Decimal("3.05"),
            export_to_cian=True,
        )

        house = Property.objects.create(
            category="house",
            operation="sale",
            external_id="HOUSE-COVER",
            address="Мытищи",
            total_area=Decimal("180"),
            land_area=Decimal("8"),
            land_area_unit="sotka",
            price=Decimal("20500000"),
            phone_number="+7 902 000-11-22",
            house_type="house",
            building_floors=2,
            building_build_year=2010,
            building_material="brick",
            gas_supply_type="border",
            sewerage_type="central",
            water_supply_type="well",
            has_electricity=True,
            power=20,
            export_to_cian=True,
        )

        land = Property.objects.create(
            category="land",
            operation="sale",
            external_id="LAND-COVER",
            address="Подмосковье",
            land_area=Decimal("12"),
            land_area_unit="sotka",
            price=Decimal("2500000"),
            phone_number="+7 903 333-44-55",
            has_electricity=True,
            power=5,
            export_to_cian=True,
        )

        commercial = Property.objects.create(
            category="commercial",
            operation="rent_long",
            external_id="COMM-COVER",
            address="Москва",
            total_area=Decimal("320"),
            price=Decimal("250000"),
            phone_number="+7 904 222-33-44",
            commercial_type="office",
            ceiling_height=Decimal("3.6"),
            is_rent_by_parts=True,
            rent_by_parts_desc="Частями",
            has_parking=True,
            parking_places=5,
            power=40,
            export_to_cian=True,
        )

        garage = Property.objects.create(
            category="garage",
            operation="sale",
            external_id="GARAGE-COVER",
            address="Химки",
            total_area=Decimal("18"),
            price=Decimal("950000"),
            phone_number="+7 905 000-77-88",
            has_electricity=True,
            power=3,
            export_to_cian=True,
        )

        for prop in (flat, house, land, commercial, garage):
            self._create_photo(prop)

        feed_result = build_cian_feed(Property.objects.order_by("external_id"))
        uncovered = {
            result.prop.external_id: sorted(result.uncovered_fields)
            for result in feed_result.objects
            if result.uncovered_fields
        }

        self.assertEqual(
            uncovered,
            {},
            f"Unexpected uncovered fields detected: {uncovered}",
        )

    def test_no_empty_tags(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            external_id="FLAT-NO-EMPTY",
            address="Москва",
            total_area=Decimal("42"),
            floor_number=4,
            price=Decimal("7200000"),
            phone_number="+7 906 555-66-77",
            export_to_cian=True,
        )
        self._create_photo(prop)

        root = _export_feed(self.client)
        obj = _find_object(root, "FLAT-NO-EMPTY")

        for element in obj.iter():
            children = list(element)
            if children:
                continue
            text = element.text or ""
            self.assertTrue(
                text.strip(),
                msg=f"Element <{element.tag}> should not be empty",
            )

    def test_flat_sale_core_and_building(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            external_id="FLAT-CORE",
            address="Москва",
            total_area=Decimal("56.7"),
            floor_number=12,
            flat_rooms_count=2,
            windows_view_type="yard",
            building_floors=16,
            building_build_year=2012,
            building_material="monolith",
            building_ceiling_height=Decimal("2.90"),
            building_passenger_lifts=1,
            building_cargo_lifts=0,
            building_series="П-44",
            building_has_garbage_chute=True,
            building_parking="подземная",
            price=Decimal("13500000"),
            phone_number="+7 (999) 111-22-33",
            export_to_cian=True,
        )
        self._create_photo(prop)

        root = _export_feed(self.client)
        obj = _find_object(root, "FLAT-CORE")

        self.assertEqual(obj.findtext("FlatRoomsCount"), "2")
        self.assertEqual(obj.findtext("WindowsViewType"), "yard")

        building = obj.find("Building")
        self.assertIsNotNone(building)
        self.assertEqual(building.findtext("FloorsCount"), "16")
        self.assertEqual(building.findtext("BuildYear"), "2012")
        self.assertEqual(building.findtext("MaterialType"), "monolith")
        self.assertEqual(building.findtext("CeilingHeight"), "2.9")
        self.assertEqual(building.findtext("Series"), "П-44")
        self.assertEqual(building.findtext("HasGarbageChute"), "true")
        self.assertEqual(building.findtext("Parking"), "подземная")

    def test_house_sale_land_wc_building(self):
        prop = Property.objects.create(
            category="house",
            operation="sale",
            external_id="HOUSE-WC",
            address="Истра",
            total_area=Decimal("150"),
            land_area=Decimal("6.5"),
            land_area_unit="sotka",
            wc_location="inside",
            heating_type="gas",
            land_category="settlements",
            permitted_land_use="individualHousingConstruction",
            price=Decimal("18500000"),
            phone_number="+7 900 000-00-00",
            export_to_cian=True,
        )
        self._create_photo(prop)

        root = _export_feed(self.client)
        obj = _find_object(root, "HOUSE-WC")

        land = obj.find("Land")
        self.assertIsNotNone(land)
        self.assertEqual(land.findtext("Area"), "6.5")
        self.assertEqual(land.findtext("AreaUnitType"), "sotka")
        self.assertEqual(obj.findtext("WcLocationType"), "inside")

    def test_flat_rent_terms_and_beds(self):
        prop = Property.objects.create(
            category="flat",
            operation="rent_long",
            external_id="FLAT-RENT",
            address="Москва",
            total_area=Decimal("48"),
            floor_number=7,
            flat_rooms_count=2,
            beds_count=3,
            lease_term_type="longTerm",
            prepay_months=1,
            deposit=Decimal("55000"),
            utilities_terms="included",
            client_fee=Decimal("0"),
            agent_fee=Decimal("0"),
            price=Decimal("55000"),
            currency="rur",
            phone_country="7",
            phone_number="8 (903) 123-45-67",
            export_to_cian=True,
        )
        self._create_photo(prop)

        root = _export_feed(self.client)
        obj = _find_object(root, "FLAT-RENT")

        bt = obj.find("BargainTerms")
        self.assertIsNotNone(bt)
        self.assertEqual(bt.findtext("LeaseTermType"), "longTerm")
        self.assertEqual(bt.findtext("PrepayMonths"), "1")
        self.assertEqual(bt.findtext("Deposit"), "55000")
        self.assertEqual(bt.findtext("UtilitiesTerms"), "included")
        self.assertEqual(bt.findtext("ClientFee"), "0")
        self.assertEqual(bt.findtext("AgentFee"), "0")
        self.assertEqual(obj.findtext("BedsCount"), "3")

        phones = obj.find("Phones")
        self.assertIsNotNone(phones)
        schema = phones.find("PhoneSchema")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.findtext("CountryCode"), "+7")
        self.assertEqual(schema.findtext("Number"), "9031234567")

    def test_room_sale_roomarea_and_count(self):
        prop = Property.objects.create(
            category="room",
            operation="sale",
            external_id="ROOM-COUNT",
            address="Москва",
            total_area=Decimal("12"),
            rooms_for_sale_count=1,
            floor_number=3,
            price=Decimal("3200000"),
            phone_number="+7 999 000-11-22",
            export_to_cian=True,
        )
        self._create_photo(prop)

        root = _export_feed(self.client)
        obj = _find_object(root, "ROOM-COUNT")

        self.assertEqual(obj.findtext("RoomArea"), "12")
        self.assertEqual(obj.findtext("RoomsForSaleCount"), "1")
