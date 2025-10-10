from decimal import Decimal
from xml.etree import ElementTree as ET

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Photo, Property


class TestCianFeedHouse(TestCase):
    def _export(self):
        response = self.client.get(reverse("export_cian"))
        self.assertEqual(response.status_code, 200)
        return response

    def _get_first_object(self, response):
        root = ET.fromstring(response.content)
        objects = root.findall("object")
        self.assertTrue(objects, "expected at least one object in feed")
        return objects[0], root

    def test_house_utilities_and_land_in_xml(self):
        prop = Property.objects.create(
            category="house",
            operation="sale",
            external_id="HOUSE-UTIL-LAND",
            address="Москва",
            total_area=Decimal("95"),
            land_area=Decimal("6"),
            land_area_unit="sotka",
            permitted_land_use="individualHousingConstruction",
            land_category="settlements",
            is_land_with_contract=True,
            sewerage_type="septic",
            water_supply_type="borehole",
            gas_supply_type="border",
            price=Decimal("10000000"),
            phone_country="7",
            phone_number="9991234567",
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="/media/photos/p.jpg", sort=10, is_default=True)
        Photo.objects.create(
            property=prop,
            full_url="https://example.com/photo2.jpg",
            sort=20,
        )

        response = self._export()
        xml_text = response.content.decode("utf-8")

        self.assertIn("<Gas><Type>border</Type></Gas>", xml_text)
        self.assertIn("<Drainage><Type>septicTank</Type></Drainage>", xml_text)
        self.assertIn("<Water><SuburbanWaterType>borehole</SuburbanWaterType></Water>", xml_text)

        self.assertIn("<Land>", xml_text)
        self.assertIn("<Area>6</Area>", xml_text)
        self.assertIn("<AreaUnitType>sotka</AreaUnitType>", xml_text)
        self.assertIn("<IsLandWithContract>true</IsLandWithContract>", xml_text)
        self.assertIn("<PermittedLandUse>individualHousingConstruction</PermittedLandUse>", xml_text)
        self.assertIn("<LandCategory>settlements</LandCategory>", xml_text)

        self.assertIn("<Phones>", xml_text)
        self.assertIn("<PhoneSchema>", xml_text)
        self.assertIn("<CountryCode>+7</CountryCode>", xml_text)
        self.assertIn("<Number>9991234567</Number>", xml_text)

        self.assertIn("<FullUrl>http", xml_text)

    def test_skip_empty_utilities_and_phones(self):
        prop = Property.objects.create(
            category="house",
            operation="sale",
            external_id="HOUSE-NOUTIL",
            address="Тверь",
            total_area=Decimal("80"),
            land_area=Decimal("5"),
            land_area_unit="sotka",
            price=Decimal("5000000"),
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="https://example.com/h.jpg", is_default=True)

        response = self._export()
        xml_text = response.content.decode("utf-8")

        self.assertNotIn("<Gas>", xml_text)
        self.assertNotIn("<Drainage>", xml_text)
        self.assertNotIn("<Water>", xml_text)
        self.assertNotIn("<Phones>", xml_text)

    def test_photo_absolute_fallback(self):
        prop = Property.objects.create(
            category="house",
            operation="sale",
            external_id="HOUSE-PHOTO",
            address="Казань",
            total_area=Decimal("70"),
            land_area=Decimal("4"),
            land_area_unit="sotka",
            price=Decimal("4200000"),
            export_to_cian=True,
        )
        Photo.objects.create(
            property=prop,
            image=SimpleUploadedFile("test.jpg", b"fake", content_type="image/jpeg"),
            is_default=True,
        )

        response = self._export()
        obj, _ = self._get_first_object(response)
        photos = obj.find("Photos")
        self.assertIsNotNone(photos)
        urls = [node.findtext("FullUrl") for node in photos.findall("PhotoSchema")]
        self.assertTrue(urls)
        for url in urls:
            self.assertTrue(url.startswith("http"))
