from django.test import Client, TestCase

from core.models import Property


class FormSaveTests(TestCase):
    def test_create_defaults_status_draft(self):
        client = Client()
        data = {
            "title": "Test house",
            "category": "house",
            "operation": "sale",
            "subtype": "house",
            "house_type": "house",
            "total_area": "120",
            "currency": "rur",
        }
        response = client.post(
            "/panel/create/?category=house&operation=sale",
            data,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        prop = Property.objects.latest("id")
        self.assertEqual(prop.status, "draft")
