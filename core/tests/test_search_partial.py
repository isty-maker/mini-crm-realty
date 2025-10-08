from django.test import TestCase
from django.urls import reverse
from core.models import Property


class PartialSearchTest(TestCase):
    def test_partial_search_multi_tokens(self):
        Property.objects.create(title="Квартира", address="Москва, Тверская 1", external_id="A123")
        url = reverse("panel_list") + "?q=Тверс мос"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Тверская", html)

    def test_partial_search_external_id(self):
        Property.objects.create(title="Офис", address="СПб, Невский 10", external_id="OFF-7788")
        url = reverse("panel_list") + "?q=7788"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("OFF-7788", html)
