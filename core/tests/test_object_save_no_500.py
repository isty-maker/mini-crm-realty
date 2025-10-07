from django.test import TestCase
from django.urls import reverse

from core.models import Property


class No500OnSaveTest(TestCase):
    def test_create_object_no_500(self):
        url = reverse("panel_create")
        response = self.client.post(url, {"title": "Тест", "address": "Москва"})
        self.assertIn(response.status_code, (200, 302, 303))

    def test_edit_object_no_500(self):
        prop = Property.objects.create(title="Тест", address="СПб")
        url = reverse("panel_edit", kwargs={"pk": prop.id})
        response = self.client.post(url, {"title": "Тест-2", "address": "СПб, Невский"})
        self.assertIn(response.status_code, (200, 302, 303))
