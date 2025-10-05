from django.test import Client, TestCase


class CreatePageTests(TestCase):
    def test_open_house_sale(self):
        response = Client().get("/panel/create/?category=house&operation=sale")
        self.assertEqual(response.status_code, 200)
