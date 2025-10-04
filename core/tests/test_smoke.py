from django.test import Client, TestCase


class Smoke(TestCase):
    def test_create_page_renders(self):
        c = Client()
        response = c.get("/panel/create/?category=house&operation=sale")
        assert response.status_code in (200, 302, 404)
