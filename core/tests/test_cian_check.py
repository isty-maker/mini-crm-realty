from django.test import TestCase
from django.urls import reverse

from core.models import Property


class TestCianCheck(TestCase):
    def test_missing_price_phone_photo_listed(self):
        Property.objects.create(
            category="flat",
            operation="sale",
            title="X",
            address="A",
            total_area=30,
            export_to_cian=True,
        )
        resp = self.client.get(reverse("export_cian_check"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("Price", html)
        self.assertIn("Phone (at least one)", html)
        self.assertIn("Photo (at least one)", html)
