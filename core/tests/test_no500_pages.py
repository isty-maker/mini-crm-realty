from django.test import TestCase
from django.urls import reverse

from core.models import Property


class No500PagesTest(TestCase):
    def test_new_page_get(self):
        resp = self.client.get(reverse("panel_new"))
        self.assertEqual(resp.status_code, 200)

    def test_create_invalid_keeps_page(self):
        resp = self.client.post(reverse("panel_create"), {"title": ""})
        self.assertIn(resp.status_code, (200, 302, 303))

    def test_edit_get(self):
        p = Property.objects.create(title="Тест", address="Москва")
        resp = self.client.get(reverse("panel_edit", kwargs={"pk": p.id}))
        self.assertEqual(resp.status_code, 200)
