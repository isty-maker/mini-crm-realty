from decimal import Decimal
from xml.etree import ElementTree as ET

from django.test import TestCase
from django.urls import reverse

from core.models import Photo, Property


def _export_first_object(client):
    resp = client.get(reverse("export_cian"))
    return resp


class TestCianOptionalFields(TestCase):
    def _create_photo(self, prop):
        Photo.objects.create(
            property=prop,
            full_url="https://example.com/photo.jpg",
            is_default=True,
        )

    def _get_exported_object(self):
        resp = _export_first_object(self.client)
        self.assertEqual(resp.status_code, 200)
        root = ET.fromstring(resp.content)
        objs = root.findall("object")
        self.assertTrue(objs, "Expected at least one exported object")
        return objs[0]

    def test_includes_optional_when_present(self):
        prop = Property.objects.create(
            category="commercial",
            operation="rent_long",
            title="Test property",
            address="Address",
            total_area=Decimal("123.4"),
            external_id="CIAN-OPT-1",
            phone_number="+7 (999) 111-22-33",
            price=Decimal("50000"),
            export_to_cian=True,
            loggias_count=1,
            balconies_count=2,
            room_type="both",
            is_euro_flat=True,
            is_apartments=True,
            is_penthouse=True,
            layout_photo_url="https://example.com/layout.jpg",
            building_floors=25,
            building_build_year=2005,
            building_material="brick",
            building_ceiling_height=Decimal("3.20"),
            building_passenger_lifts=3,
            building_cargo_lifts=1,
            windows_view_type="yardAndStreet",
            separate_wcs_count=1,
            combined_wcs_count=2,
            repair_type="euro",
            land_area=Decimal("6.5"),
            heating_type="gas",
            power=15,
            parking_places=5,
            has_parking=True,
            has_internet=True,
            has_furniture=True,
            has_kitchen_furniture=True,
            has_tv=True,
            has_washer=True,
            has_conditioner=True,
            has_refrigerator=True,
            has_dishwasher=True,
            has_shower=True,
            has_phone=True,
            has_ramp=True,
            has_bathtub=True,
            is_rent_by_parts=True,
            rent_by_parts_desc="Частями",
        )
        self._create_photo(prop)

        obj = self._get_exported_object()

        self.assertEqual(obj.findtext("LoggiasCount"), "1")
        self.assertEqual(obj.findtext("BalconiesCount"), "2")
        self.assertEqual(obj.findtext("RoomType"), "both")
        self.assertEqual(obj.findtext("IsEuroFlat"), "true")
        self.assertEqual(obj.findtext("IsApartments"), "true")
        self.assertEqual(obj.findtext("IsPenthouse"), "true")

        layout = obj.find("LayoutPhoto")
        self.assertIsNotNone(layout)
        self.assertEqual(layout.findtext("FullUrl"), "https://example.com/layout.jpg")

        self.assertEqual(obj.findtext("FloorsCount"), "25")
        self.assertEqual(obj.findtext("BuildYear"), "2005")
        self.assertEqual(obj.findtext("MaterialType"), "brick")
        self.assertEqual(obj.findtext("CeilingHeight"), "3.2")
        self.assertEqual(obj.findtext("PassengerLiftsCount"), "3")
        self.assertEqual(obj.findtext("CargoLiftsCount"), "1")

        self.assertEqual(obj.findtext("WindowsViewType"), "yardAndStreet")
        self.assertEqual(obj.findtext("SeparateWcsCount"), "1")
        self.assertEqual(obj.findtext("CombinedWcsCount"), "2")
        self.assertEqual(obj.findtext("RepairType"), "euro")

        self.assertEqual(obj.findtext("HeatingType"), "gas")
        self.assertEqual(obj.findtext("Power"), "15")
        self.assertEqual(obj.findtext("ParkingPlacesCount"), "5")
        self.assertEqual(obj.findtext("HasParking"), "true")

        self.assertEqual(obj.findtext("HasInternet"), "true")
        self.assertEqual(obj.findtext("HasFurniture"), "true")
        self.assertEqual(obj.findtext("HasKitchenFurniture"), "true")
        self.assertEqual(obj.findtext("HasTv"), "true")
        self.assertEqual(obj.findtext("HasWasher"), "true")
        self.assertEqual(obj.findtext("HasConditioner"), "true")
        self.assertEqual(obj.findtext("HasRefrigerator"), "true")
        self.assertEqual(obj.findtext("HasDishwasher"), "true")
        self.assertEqual(obj.findtext("HasShower"), "true")
        self.assertEqual(obj.findtext("HasPhone"), "true")
        self.assertEqual(obj.findtext("HasRamp"), "true")
        self.assertEqual(obj.findtext("HasBathtub"), "true")

        self.assertEqual(obj.findtext("IsRentByParts"), "true")
        self.assertEqual(obj.findtext("RentByPartsDescription"), "Частями")

    def test_skips_optional_when_empty(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            title="Empty optional",
            address="Address",
            total_area=Decimal("45"),
            external_id="CIAN-OPT-2",
            phone_number="+7 912 111-22-33",
            price=Decimal("1500000"),
            export_to_cian=True,
        )
        self._create_photo(prop)

        obj = self._get_exported_object()

        for tag in [
            "LoggiasCount",
            "BalconiesCount",
            "RoomType",
            "IsEuroFlat",
            "IsApartments",
            "IsPenthouse",
            "FloorsCount",
            "BuildYear",
            "MaterialType",
            "CeilingHeight",
            "PassengerLiftsCount",
            "CargoLiftsCount",
            "WindowsViewType",
            "SeparateWcsCount",
            "CombinedWcsCount",
            "RepairType",
            "HeatingType",
            "Power",
            "ParkingPlacesCount",
            "HasParking",
            "HasInternet",
            "HasFurniture",
            "HasKitchenFurniture",
            "HasTv",
            "HasWasher",
            "HasConditioner",
            "HasRefrigerator",
            "HasDishwasher",
            "HasShower",
            "HasPhone",
            "HasRamp",
            "HasBathtub",
            "IsRentByParts",
            "RentByPartsDescription",
        ]:
            self.assertIsNone(obj.find(tag), f"{tag} should not be exported when empty")

        self.assertIsNone(obj.find("LayoutPhoto"))

    def test_layout_photo_block(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            title="With layout",
            address="Address",
            total_area=Decimal("60"),
            external_id="CIAN-OPT-3",
            phone_number="+7 912 555-66-77",
            price=Decimal("2500000"),
            export_to_cian=True,
            layout_photo_url="https://example.com/layout-2.jpg",
        )
        self._create_photo(prop)

        obj = self._get_exported_object()

        layout = obj.find("LayoutPhoto")
        self.assertIsNotNone(layout)
        self.assertEqual(layout.findtext("FullUrl"), "https://example.com/layout-2.jpg")
