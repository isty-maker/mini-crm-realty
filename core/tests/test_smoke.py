from decimal import Decimal

from django.test import Client, TestCase

from core.models import Property


class Smoke(TestCase):
    def test_create_page_renders(self):
        c = Client()
        response = c.get("/panel/create/?category=house&operation=sale")
        assert response.status_code == 200

    def test_export_check_page(self):
        Property.objects.create(
            title="Smoke House",
            external_id="SMOKE-CHECK",
            category="house",
            operation="sale",
            subtype="house",
            total_area=Decimal("120"),
            export_to_cian=True,
        )
        response = self.client.get("/panel/export/cian/check")
        assert response.status_code == 200
        assert "Smoke House" in response.content.decode("utf-8")

    def test_export_xml(self):
        Property.objects.create(
            title="Smoke Flat",
            external_id="SMOKE-XML",
            category="flat",
            operation="sale",
            subtype="apartment",
            total_area=Decimal("45"),
            export_to_cian=True,
        )
        response = self.client.get("/panel/export/cian")
        assert response.status_code == 200
        assert b"<Feed" in response.content


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
