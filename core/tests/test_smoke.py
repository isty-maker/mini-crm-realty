from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase

from core.models import Property


class ExportSmokeTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_create_page_house_sale_200(self):
        response = self.client.get("/panel/create/?category=house&operation=sale")
        self.assertEqual(response.status_code, 200)

    def test_cian_check_200(self):
        Property.objects.create(
            title="X",
            category="house",
            operation="sale",
            external_id="AGTEST1",
            export_to_cian=True,
            total_area=120,
        )
        response = self.client.get("/panel/export/cian/check/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8").lower()
        self.assertIn("экспорт", body)

    def test_cian_export_200_and_has_feed(self):
        Property.objects.create(
            title="X2",
            category="flat",
            operation="sale",
            external_id="AGTEST2",
            export_to_cian=True,
            total_area=45,
        )
        response = self.client.get("/panel/export/cian/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<Feed", response.content)
        feeds_path = Path(settings.MEDIA_ROOT) / "feeds" / "cian.xml"
        self.assertTrue(feeds_path.exists())
