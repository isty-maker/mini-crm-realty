from django.test import TestCase
from django.urls import reverse

from core.models import Property


class PanelListSearchTest(TestCase):
    def test_search_by_address(self):
        Property.objects.create(title="Квартира", address="Москва, Тверская 1")
        url = reverse("panel_list") + "?q=Тверская"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Тверская", resp.content.decode())
