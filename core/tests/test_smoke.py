from django.test import Client, TestCase

from core.models import Property


class Smoke(TestCase):
    def test_create_page_renders(self):
        c = Client()
        response = c.get("/panel/create/?category=house&operation=sale")
        assert response.status_code in (200, 302, 404)


class FlagsExistenceTests(TestCase):
    def test_domklik_flag_exists_and_defaults(self):
        prop = Property.objects.create(
            title="T",
            category="flat",
            operation="sale",
            external_id="AGTEST_FLAG",
        )
        assert hasattr(prop, "export_to_domklik")
        assert prop.export_to_domklik is False
