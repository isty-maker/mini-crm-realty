from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(SHARED_KEY="kontinent")
class ExportAuthTest(TestCase):
    def test_export_is_public(self):
        url = reverse("export_cian")
        self.assertEqual(self.client.get(url).status_code, 200)

    @override_settings(SHARED_KEY="kontinent")
    def test_export_accepts_header(self):
        url = reverse("export_cian")
        resp = self.client.get(url, **{"HTTP_X_SHARED_KEY": "kontinent"})
        self.assertEqual(resp.status_code, 200)
