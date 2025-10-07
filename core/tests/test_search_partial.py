from django.test import TestCase
from django.urls import reverse
from core.models import Property


class PartialSearchTest(TestCase):
    def test_search_by_partial_tokens(self):
        Property.objects.create(title="Квартира", address="Москва, Тверская 1", external_id="A123")
        url = reverse("panel_list") + "?q=тверс мос"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode().lower()
        self.assertIn("тверская", html)

    def test_search_by_external_id(self):
        Property.objects.create(title="Офис", address="СПб, Невский 10", external_id="OFF-7788")
        url = reverse("panel_list") + "?q=7788"
        resp = self.client.get(url)
        html = resp.content.decode()
        # может быть отображён external_id или адрес
        self.assertTrue("OFF-7788" in html or "Невский" in html)
