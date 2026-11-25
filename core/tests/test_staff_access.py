from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(CRM_REQUIRE_STAFF_LOGIN=True)
class StaffAccessTests(TestCase):
    def test_anonymous_panel_and_diagnostics_are_protected(self):
        for path in ("/panel/", "/panel/edit/1/", "/panel/objects/1/", "/panel/objects/1/photos/",
                     "/panel/export/cian/check/", "/healthz/mediainfo/", "/healthz/dbinfo/", "/healthz/logtail/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/crm/login/?next="))
                self.assertIn("no-store", response["Cache-Control"])
        for path in ("/panel/create/", "/panel/1/price/", "/panel/1/toggle-export/cian/",
                     "/panel/photo/1/delete/", "/panel/objects/1/sections/deal/"):
            self.assertEqual(self.client.post(path).status_code, 403)

    def test_healthz_and_xml_get_head_stay_public(self):
        self.assertEqual(self.client.get("/healthz/").status_code, 200)
        with patch("core.views.build_cian_feed") as build, patch(
            "core.management.commands.generate_cian_feed.generate_and_save_feed", return_value=""
        ):
            build.return_value.xml = b"<Feed/>"
            for path in ("/panel/export/cian/", "/panel/export/domklik/"):
                self.assertEqual(self.client.get(path).status_code, 200)
                self.assertEqual(self.client.head(path).status_code, 200)

    def test_staff_can_sign_in_and_non_staff_is_denied(self):
        user_model = get_user_model()
        employee = user_model.objects.create_user(username="staff-fixture", password="local-test-credential", is_staff=True)
        other = user_model.objects.create_user(username="nonstaff-fixture", password="local-test-credential")
        login = reverse("crm_staff_login")
        response = self.client.post(login, {"username": other.username, "password": "local-test-credential"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "не имеет доступа")
        self.client.force_login(other)
        self.assertEqual(self.client.get("/panel/").status_code, 403)
        self.client.logout()
        self.assertRedirects(self.client.post(login, {"username": employee.username, "password": "local-test-credential"}), "/panel/")
        self.assertIn("no-store", self.client.get("/panel/")["Cache-Control"])
        logout = reverse("crm_staff_logout")
        self.assertEqual(self.client.get(logout).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(employee)
        self.assertEqual(csrf_client.post(logout).status_code, 403)
        self.assertRedirects(self.client.post(logout), login)
