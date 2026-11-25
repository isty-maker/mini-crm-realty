from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.utils import timezone

from crm_access.invitations import issue
from crm_access.models import StaffInvitation

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

    @override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True, CRM_STAFF_SESSION_DAYS=90)
    def test_invitation_get_does_not_consume_and_post_uses_csrf_https_and_single_use(self):
        employee = get_user_model().objects.create_user(username="fixture", is_staff=True)
        invitation, token = issue(employee, 1)
        self.assertNotEqual(invitation.digest, token)
        client = Client(enforce_csrf_checks=True)
        url = reverse("crm_staff_login")
        response = client.get(url, secure=True)
        self.assertIn("no-store", response["Cache-Control"])
        invitation.refresh_from_db()
        self.assertIsNone(invitation.used_at)
        self.assertEqual(client.post(url, {"invitation": token}, secure=True).status_code, 403)
        csrf = client.cookies["csrftoken"].value
        blocked = client.post(url, {"invitation": token, "csrfmiddlewaretoken": csrf})
        self.assertEqual(blocked.status_code, 403)
        result = client.post(url, {"invitation": token, "csrfmiddlewaretoken": csrf}, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result["Location"], "/panel/")
        cookie = result.cookies["sessionid"]
        self.assertTrue(cookie["secure"] and cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["max-age"], 90 * 86400)
        self.assertEqual(Client().post(url, {"invitation": token}, secure=True).status_code, 403)
        call_command("crm_invite", employee.username, "--disable")
        self.assertEqual(client.get("/panel/", secure=True).status_code, 302)

    def test_expired_revoked_and_disabled_accounts_cannot_accept(self):
        user = get_user_model().objects.create_user(username="fixture", is_staff=True)
        url = reverse("crm_staff_login")
        for values in ({"expires_at": timezone.now() - timedelta(days=1)}, {"revoked_at": timezone.now()}):
            invitation, token = issue(user, 1)
            StaffInvitation.objects.filter(pk=invitation.pk).update(**values)
            self.assertEqual(self.client.post(url, {"invitation": token}, secure=True).status_code, 403)
        invitation, token = issue(user, 1)
        call_command("crm_invite", user.username, "--revoke", invitation.pk)
        self.assertEqual(self.client.post(url, {"invitation": token}, secure=True).status_code, 403)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("crm_staff_logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("crm_staff_logout")).status_code, 302)
