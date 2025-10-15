from decimal import Decimal
from xml.etree import ElementTree as ET

from django.test import TestCase
from django.urls import reverse

from core.models import Photo, Property


def _export_feed(client):
    response = client.get(reverse("export_cian"))
    assert response.status_code == 200
    return ET.fromstring(response.content)


def _find_object(root, external_id):
    for obj in root.findall("object"):
        if obj.findtext("ExternalId") == external_id:
            return obj
    raise AssertionError(f"object with ExternalId={external_id} not found")


class CianFeedStructureTests(TestCase):
    def test_feed_root_and_version_ok(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            external_id="TEST-ROOT",
            address="Адрес",
            total_area=Decimal("42"),
            floor_number=5,
            price=Decimal("1000000"),
            phone_number="+7 (900) 000-00-00",
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="http://example.com/p.jpg", is_default=True)

        root = _export_feed(self.client)
        self.assertEqual(root.tag, "feed")
        self.assertEqual(root.findtext("feed_version"), "2")
        objects = root.findall("object")
        self.assertTrue(objects)

    def test_photo_urls_are_absolute(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            external_id="PHOTO-ABS",
            address="Москва",
            total_area=Decimal("33.5"),
            floor_number=3,
            price=Decimal("3300000"),
            phone_number="+7 999 111-22-33",
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="/media/photos/1.jpg", sort=10)
        Photo.objects.create(property=prop, full_url="http://cdn.example.com/abs2.jpg", sort=20)

        root = _export_feed(self.client)
        obj = _find_object(root, "PHOTO-ABS")
        photos = obj.find("Photos")
        self.assertIsNotNone(photos)
        urls = [node.findtext("FullUrl") for node in photos.findall("PhotoSchema")]
        self.assertTrue(urls)
        for url in urls:
            self.assertTrue(url.startswith("http"))
            self.assertIn("testserver", url) if url.startswith("http://testserver") else None

    def test_flat_sale_layout_and_sale_type(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            external_id="FLAT-LAYOUT",
            address="Москва",
            total_area=Decimal("55"),
            floor_number=7,
            price=Decimal("7200000"),
            phone_number="+7 905 000-00-00",
            room_type="both",
            sale_type="alternative",
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="http://example.com/p.jpg")

        root = _export_feed(self.client)
        obj = _find_object(root, "FLAT-LAYOUT")
        self.assertEqual(obj.findtext("RoomType"), "both")
        bargain_terms = obj.find("BargainTerms")
        self.assertIsNotNone(bargain_terms)
        self.assertEqual(bargain_terms.findtext("SaleType"), "alternative")

    def test_house_sale_core_fields_present(self):
        prop = Property.objects.create(
            category="house",
            operation="sale",
            external_id="HOUSE-CORE",
            address="Нижний Новгород",
            total_area=Decimal("120"),
            land_area=Decimal("6.5"),
            land_area_unit="sotka",
            building_floors=2,
            building_material="brick,wood",
            building_build_year=2005,
            price=Decimal("8500000"),
            phone_number="+7 904 111-22-33",
            wc_location="inside",
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="http://example.com/h1.jpg")

        root = _export_feed(self.client)
        obj = _find_object(root, "HOUSE-CORE")
        self.assertEqual(obj.findtext("TotalArea"), "120")
        land = obj.find("Land")
        self.assertIsNotNone(land)
        self.assertEqual(land.findtext("Area"), "6.5")
        self.assertEqual(land.findtext("AreaUnitType"), "sotka")
        building = obj.find("Building")
        self.assertIsNotNone(building)
        self.assertEqual(building.findtext("FloorsCount"), "2")
        material_types = obj.find("MaterialTypes")
        self.assertIsNotNone(material_types)
        exported_materials = [node.text for node in material_types.findall("MaterialType")]
        self.assertEqual(exported_materials, ["brick", "wood"])
        self.assertEqual(obj.findtext("BuildYear"), "2005")

    def test_house_rent_category_and_materials(self):
        prop = Property.objects.create(
            category="house",
            operation="rent_long",
            external_id="HOUSE-RENT",
            address="Киров",
            total_area=Decimal("80"),
            building_floors=3,
            building_material="aerocreteBlock,wood",
            heating_type="autonomousGas",
            price=Decimal("45000"),
            phone_number="+7 910 555-66-77",
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="http://example.com/hr.jpg")

        root = _export_feed(self.client)
        obj = _find_object(root, "HOUSE-RENT")
        self.assertEqual(obj.findtext("Category"), "houseRent")
        building = obj.find("Building")
        self.assertIsNotNone(building)
        self.assertEqual(building.findtext("FloorsCount"), "3")
        materials = obj.find("MaterialTypes")
        self.assertIsNotNone(materials)
        exported = [node.text for node in materials.findall("MaterialType")]
        self.assertEqual(exported, ["aerocreteBlock", "wood"])
        self.assertEqual(obj.findtext("HeatingType"), "autonomousGas")

    def test_no_metro_no_jk_in_feed(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            external_id="NO-METRO",
            address="Москва",
            total_area=Decimal("40"),
            floor_number=4,
            price=Decimal("5000000"),
            phone_number="+7 905 999-88-77",
            jk_name="ЖК Пример",
            jk_id=123,
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="http://example.com/p.jpg")

        root = _export_feed(self.client)
        xml_text = ET.tostring(root, encoding="utf-8").decode("utf-8").lower()
        self.assertNotIn("<jk", xml_text)
        self.assertNotIn("underground", xml_text)

        obj = _find_object(root, "NO-METRO")
        tags = [element.tag.lower() for element in obj.iter()]
        self.assertTrue(all("metro" not in tag for tag in tags))

    def test_flat_sale_rooms_and_windows_tags(self):
        prop = Property.objects.create(
            category="flat",
            operation="sale",
            external_id="FLAT-TAGS",
            address="Москва",
            flat_rooms_count=2,
            windows_view_type="yard",
            total_area=Decimal("45"),
            floor_number=6,
            price=Decimal("5000000"),
            currency="rur",
            phone_number="+7 900 000-00-00",
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="http://example.com/p.jpg")

        root = _export_feed(self.client)
        obj = _find_object(root, "FLAT-TAGS")
        self.assertEqual(obj.findtext("FlatRoomsCount"), "2")
        self.assertEqual(obj.findtext("WindowsViewType"), "yard")

    def test_house_wc_location_type_and_phone_plus(self):
        prop = Property.objects.create(
            category="house",
            operation="sale",
            external_id="HOUSE-TAGS",
            address="Тюмень",
            total_area=Decimal("90"),
            land_area=Decimal("5"),
            land_area_unit="sotka",
            wc_location="inside",
            price=Decimal("6500000"),
            currency="rur",
            phone_country="7",
            phone_number="9991234567",
            export_to_cian=True,
        )
        Photo.objects.create(property=prop, full_url="http://example.com/h.jpg")

        root = _export_feed(self.client)
        obj = _find_object(root, "HOUSE-TAGS")
        self.assertEqual(obj.findtext("WcLocationType"), "inside")
        phones = obj.find("Phones")
        self.assertIsNotNone(phones)
        phone_nodes = phones.findall("PhoneSchema")
        self.assertTrue(phone_nodes)
        self.assertEqual(phone_nodes[0].findtext("CountryCode"), "+7")
        self.assertEqual(phone_nodes[0].findtext("Number"), "9991234567")
