from django.test import TestCase
from django.urls import reverse

from core.models import Property


class PanelListPartialSearchTest(TestCase):
    def test_search_by_partial_address(self):
        Property.objects.create(title="Квартира", address="Москва, Тверская 1")
        url = reverse("panel_list") + "?q=Тверск"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Тверская", html)

    def test_search_by_external_id_or_address(self):
        Property.objects.create(
            title="Офис",
            address="Санкт-Петербург, Невский 10",
            external_id="OFF-7788",
        )
        url = reverse("panel_list") + "?q=7788"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertTrue(("OFF-7788" in html) or ("Невский 10" in html))
