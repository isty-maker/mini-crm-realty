from xml.etree import ElementTree as ET

from django.test import TestCase
from django.urls import reverse

from core.models import Photo, Property


class TestCianFeedMinimal(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(
            category="flat",
            operation="sale",
            title="T",
            address="A",
            total_area=42,
            external_id="X1",
            phone_number="+7 999 111-22-33",
            price=1_000_000,
            export_to_cian=True,
        )
        Photo.objects.create(
            property=self.prop,
            full_url="https://example.com/p.jpg",
            is_default=True,
        )

    def test_export_generates_valid_xml(self):
        resp = self.client.get(reverse("export_cian"))
        self.assertEqual(resp.status_code, 200)
        xml = resp.content
        root = ET.fromstring(xml)
        self.assertEqual(root.findtext("feed_version"), "2")
        objs = root.findall("object")
        self.assertTrue(objs, "at least one object expected")
        obj = objs[0]
        self.assertEqual(obj.findtext("Category"), "flatSale")
        self.assertIsNotNone(obj.find("Phones"))
        self.assertIsNotNone(obj.find("Photos"))
        self.assertIsNotNone(obj.find("BargainTerms"))
