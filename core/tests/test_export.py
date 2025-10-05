from django.test import Client, TestCase
from core.models import Property


class ExportTests(TestCase):
    def test_check_page(self):
        Property.objects.create(
            title="X",
            category="house",
            operation="sale",
            external_id="AG1",
            export_to_cian=True,
            total_area=123,
        )
        response = Client().get("/panel/export/cian/check")
        self.assertEqual(response.status_code, 200)

    def test_generate_xml(self):
        Property.objects.create(
            title="Y",
            category="flat",
            operation="sale",
            external_id="AG2",
            export_to_cian=True,
            total_area=45,
        )
        response = Client().get("/panel/export/cian")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<Feed", response.content)
