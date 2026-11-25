import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Photo, Property
from core.workspace_models import PropertyWorkspace, PropertyChange

from crm_api.access import issue_key
from crm_api.models import IdempotentWrite


ROOT = "/api/v1/objects/"


@override_settings(CRM_REQUIRE_STAFF_LOGIN=True)
class PassportAPITests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username="synthetic-api-user", is_staff=True)
        self.key, secret = issue_key(self.actor, "synthetic key", can_write=True, can_identify=True)
        self.api = Client(enforce_csrf_checks=True, HTTP_AUTHORIZATION=f"Bearer {secret}")
        path = settings.BASE_DIR / "docs/examples/crm-api-passport.json"
        self.passport = json.loads(Path(path).read_text())

    def post(self, url, data, version=None, idempotency="fixture", client=None):
        headers = {"Idempotency-Key": idempotency}
        if version:
            headers["If-Match"] = version
        return (client or self.api).post(url, data, content_type="application/json", secure=True, headers=headers)

    def patch(self, url, data, version=None):
        headers = {"If-Match": version} if version else {}
        return self.api.patch(url, data, content_type="application/json", secure=True, headers=headers)

    def create(self):
        response = self.post(ROOT, {"listing": self.passport["create"]})
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def test_passport_round_trip_editor_conflict_and_idempotent_collections(self):
        created = self.create()
        pk = created.json()["id"]
        url = f"{ROOT}{pk}/"
        prop = Property.objects.get(pk=pk)
        self.assertEqual(prop.status, "draft")
        self.assertEqual((prop.cadastral_number, prop.flat_number), ("00:00:0000000:7", "Тест-7"))
        self.assertFalse(prop.export_to_cian or prop.export_to_domklik)
        self.assertEqual(self.post(ROOT, {"listing": self.passport["create"]})["Idempotency-Replayed"], "true")
        self.assertEqual(self.post(ROOT, {"listing": self.passport["create"]}, idempotency="other").status_code, 409)
        fresh = self.api.get(url, secure=True)
        before = prop.staff_changes.count()
        dry = self.patch(url + "?dry_run=1", self.passport["update"], fresh["ETag"])
        self.assertEqual(dry.status_code, 200, dry.content)
        self.assertEqual(dry.json()["changes"]["listing"]["price"], {"old": None, "new": "6350000.25"})
        self.assertEqual(prop.staff_changes.count(), before)
        self.assertFalse(PropertyWorkspace.objects.filter(property=prop).exists())
        self.assertEqual(self.patch(url, self.passport["update"]).status_code, 428)
        saved = self.patch(url, self.passport["update"], dry["ETag"])
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(saved.json()["listing"]["price"], "6350000.25")
        self.assertEqual(saved.json()["workspace"]["legal"]["owner_count"], 2)
        types = {item["slug"]: item["id"] for item in
                 self.api.get("/api/v1/document-types/", secure=True).json()["document_types"]}
        files = {}
        for scope in ("files", "bases", "owners", "documents", "notes"):
            for index, values in enumerate(self.passport[scope]):
                data = values.copy()
                if scope == "documents":
                    data["document_type"] = types[data.pop("type")]
                    if "file" in data:
                        data["original"] = files[data.pop("file")]
                namespace = f"{scope}-{index}"
                route = url + scope + "/"
                new_version = self.api.get(url, secure=True)["ETag"]
                preview = self.post(route + "?dry_run=1", data, new_version, namespace)
                self.assertEqual(preview.status_code, 200, preview.content)
                response = self.post(route, data, preview["ETag"], namespace)
                self.assertEqual(response.status_code, 201, response.content)
                repeated = self.post(route, data, preview["ETag"], namespace)
                self.assertEqual(repeated.status_code, 200, repeated.content)
                self.assertEqual(repeated.json()["id"], response.json()["id"])
                if scope == "files":
                    files[data["file_id"]] = response.json()["id"]
        current = self.api.get(url, secure=True)
        self.assertEqual(len(current.json()["collections"]["owners"]), 2)
        self.assertEqual(len(current.json()["collections"]["documents"]), 5)
        self.assertEqual(current.json()["collections"]["notes"][0]["author_id"], self.actor.pk)
        browser = Client()
        browser.force_login(self.actor)
        card = browser.get(reverse("panel_detail", args=[pk]))
        self.assertContains(card, "SYNTHETIC-PRIVATE")
        self.assertContains(card, "Учебная заметка")
        legal = reverse("panel_private_record", args=[pk, "legal"])
        version = browser.get(legal).context["private_editor"]["version"]
        self.assertEqual(browser.post(legal, {"version": version, "legal_comments": "Обновили на показе"}).status_code, 302)
        stale = self.patch(url, {"workspace": {"legal": {"legal_comments": "Старый паспорт"}}}, current["ETag"])
        self.assertEqual(stale.status_code, 409)
        current = self.api.get(url, secure=True)
        self.assertEqual(current.json()["workspace"]["legal"]["legal_comments"], "Обновили на показе")
        refresh = self.passport["refresh_example"]
        dry_refresh = self.patch(url + "?dry_run=1", refresh, current["ETag"])
        self.assertEqual(dry_refresh.json()["changes"]["listing"]["flat_number"], {"old": "Тест-7", "new": "Тест-7А"})
        self.assertEqual(self.patch(url, refresh, dry_refresh["ETag"]).status_code, 200)
        current = self.api.get(url, secure=True)
        self.assertEqual(current.json()["listing"]["cadastral_number"], "00:00:0000000:7")
        self.assertEqual(current.json()["workspace"]["legal"]["legal_comments"], "Обновили на показе")
        self.assertEqual(len(current.json()["collections"]["owners"]), 2)
        note = current.json()["collections"]["notes"][0]
        note_url = url + f'notes/{note["id"]}/'
        note_response = self.api.get(note_url, secure=True)
        self.assertEqual(self.patch(note_url, {"text": "Уточнено"}, note_response["ETag"]).status_code, 200)
        current = self.api.get(url, secure=True)
        self.assertEqual(len(current.json()["collections"]["notes"]), 1)
        self.assertFalse(current.json()["listing"]["export_to_cian"] or current.json()["listing"]["export_to_domklik"])
        self.assertGreater(IdempotentWrite.objects.count(), 5)

    def test_access_field_types_and_atomic_failure(self):
        created = self.create()
        url = f'{ROOT}{created.json()["id"]}/'
        self.assertEqual(self.api.get(url).status_code, 403)
        self.assertEqual(Client().get(url, {"token": "fixture"}, secure=True).status_code, 401)
        _, read_secret = issue_key(self.actor, "synthetic reader")
        reader = Client(HTTP_AUTHORIZATION=f"Bearer {read_secret}")
        self.assertIn("no-store", reader.get(url, secure=True)["Cache-Control"])
        self.assertEqual(self.post(ROOT, {"listing": {}}, client=reader).status_code, 403)
        result = self.patch(url, {"listing": {"price": "10"}, "workspace": {"legal": {"owner_count": -1}}}, created["ETag"])
        self.assertEqual(result.status_code, 422)
        self.assertIsNone(self.api.get(url, secure=True).json()["listing"]["price"])
        for data in ({"listing": {"price": 0.4}}, {"listing": {"address": None}},
                     {"listing": {"export_to_cian": True}}, {"owners": []}):
            self.assertEqual(self.patch(url, data, created["ETag"]).status_code, 422)
        self.key.revoked_at = timezone.now()
        self.key.save(update_fields=["revoked_at"])
        self.assertEqual(self.api.get(url, secure=True).status_code, 401)

    def test_identifier_scope_and_duplicate_policy(self):
        created = self.create()
        listing = self.passport["create"]
        other = {**listing, "flat_number": "Тест-8", "cadastral_number": "00:00:0000000:8"}
        self.assertEqual(self.post(ROOT, {"listing": other}, idempotency="different flat").status_code, 400)
        self.assertEqual(self.post(ROOT, {"listing": other}, idempotency="different-flat").status_code, 201)
        exact = {"listing": {**listing, "address": "Другой корпус"}, "confirm_possible_duplicate": True}
        self.assertEqual(self.post(ROOT + "?dry_run=1", exact).json()["error"]["code"], "duplicate_identity")
        self.assertEqual(self.post(ROOT, exact, idempotency="same-cad").status_code, 409)
        partial = {"listing": {**listing, "address": "Синтетический корпус", "flat_number": "", "cadastral_number": ""}}
        self.assertTrue(self.post(ROOT + "?dry_run=1", partial).json()["confirmation_required"])
        self.assertEqual(self.post(ROOT, partial, idempotency="partial").status_code, 409)
        confirmed = {**partial, "confirm_possible_duplicate": True}
        self.assertEqual(self.post(ROOT, confirmed, idempotency="partial").status_code, 201)
        self.assertEqual(self.post(ROOT, confirmed, idempotency="partial")["Idempotency-Replayed"], "true")
        self.assertEqual(self.post(ROOT, partial, idempotency="partial").json()["error"]["code"], "idempotency_conflict")
        url = f'{ROOT}{created.json()["id"]}/'
        _, secret = issue_key(self.actor, "normal writer", can_write=True)
        limited = Client(HTTP_AUTHORIZATION=f"Bearer {secret}")
        self.assertNotIn("flat_number", limited.get(url, secure=True).json()["listing"])
        denied = limited.patch(url, {"listing": {"flat_number": "9"}}, content_type="application/json",
                               secure=True, HTTP_IF_MATCH=created["ETag"])
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.patch(url, {"listing": {"cadastral_number": "wrong"}}, created["ETag"]).status_code, 422)

    def test_dry_run_checks_creation_constraints_and_rolls_back_atomic_patch(self):
        item = self.create()
        url = f'{ROOT}{item.json()["id"]}/'
        counts = lambda: (IdempotentWrite.objects.count(), PropertyChange.objects.count(), PropertyWorkspace.objects.count())
        initial = counts()
        for scope, payload in (("bases", {}), ("documents", {"document_type": 987654}), ("owners", {"name": ""})):
            dry = self.post(f"{url}{scope}/?dry_run=1", payload, item["ETag"], idempotency=scope)
            actual = self.post(f"{url}{scope}/", payload, item["ETag"], idempotency=scope)
            self.assertEqual((dry.status_code, actual.status_code), (422, 422), (dry.content, actual.content))
            self.assertEqual(dry.json()["error"]["code"], actual.json()["error"]["code"])
        self.assertEqual(counts(), initial)
        file_data = self.passport["files"][0]
        self.assertEqual(self.post(url + "files/", file_data, item["ETag"], idempotency="file").status_code, 201)
        current = self.api.get(url, secure=True)
        initial = counts()
        for suffix in ("?dry_run=1", ""):
            result = self.post(url + "files/" + suffix, file_data, current["ETag"], idempotency="duplicate-file")
            self.assertEqual(result.status_code, 422, result.content)
        self.assertEqual(counts(), initial)
        with patch("crm_api.views.save_record", side_effect=ValidationError("Simulated late validation")):
            result = self.patch(url, {"listing": {"price": "100"}, "workspace": {"status": {"work_status": "active"}}},
                                current["ETag"])
        self.assertEqual(result.status_code, 422)
        self.assertEqual(counts(), initial)
        self.assertIsNone(self.api.get(url, secure=True).json()["listing"]["price"])

    def test_retirement_and_disabled_account_keys(self):
        item = self.create()
        pk = item.json()["id"]
        url = f"{ROOT}{pk}/"
        notes = self.post(url + "notes/", {"text": "Синтетическая история"}, item["ETag"], idempotency="note")
        self.assertEqual(notes.status_code, 201)
        note_url = url + f'notes/{notes.json()["id"]}/'
        dry = self.patch(note_url + "?dry_run=1", {"retire": True}, notes["ETag"])
        self.assertEqual(dry.status_code, 200)
        self.assertTrue(self.api.get(note_url, secure=True).json()["is_current"])
        retired = self.patch(note_url, {"retire": True}, dry["ETag"])
        self.assertEqual(retired.status_code, 200)
        self.assertFalse(retired.json()["is_current"])
        self.assertEqual(self.patch(note_url, {"text": "Старая версия"}, notes["ETag"]).status_code, 409)
        audit = self.api.get(url + "changes/", secure=True).json()["items"][0]
        self.assertEqual(audit["diff"], {"is_current": {"old": True, "new": False}})
        self.assertNotIn("Синтетическая история", str(audit))
        call_command("crm_invite", self.actor.username, "--disable")
        self.actor.refresh_from_db()
        self.actor.is_active = True
        self.actor.save(update_fields=["is_active"])
        self.assertEqual(self.api.get(url, secure=True).status_code, 401)
        self.key.refresh_from_db()
        self.assertIsNotNone(self.key.revoked_at)
        _, replacement_secret = issue_key(self.actor, "replacement")
        self.assertEqual(Client(HTTP_AUTHORIZATION=f"Bearer {replacement_secret}").get(url, secure=True).status_code, 200)

    def test_public_feeds_keep_order_and_omit_private_changes(self):
        prop = Property.objects.create(category="flat", operation="sale", flat_type="apartment",
                                       total_area=40, price=100, currency="rur", address="Другой синтетический объект",
                                       export_to_cian=True, export_to_domklik=True)
        Photo.objects.create(property=prop, full_url="https://example.invalid/last.jpg", sort=2)
        Photo.objects.create(property=prop, full_url="https://example.invalid/first.jpg", is_default=True)
        url = f"{ROOT}{prop.pk}/"
        snapshot = self.api.get(url, secure=True)
        feeds = (reverse("export_cian"), reverse("export_domklik"))
        with self.settings(MEDIA_ROOT=self.temp_media()), patch(
            "core.management.commands.generate_cian_feed.is_yandex_storage_configured", return_value=False
        ), patch("core.storage.is_yandex_storage_configured", return_value=False):
            public = Client()
            outputs = [public.get(feed).content for feed in feeds]
            self.api.get(url, secure=True)
            self.assertEqual(outputs, [public.get(feed).content for feed in feeds])
            saved = self.patch(url, {"listing": {"price": "130.75"},
                                    "workspace": {"legal": {"legal_comments": "NEVER-IN-FEED"}}}, snapshot["ETag"])
            self.assertEqual(saved.status_code, 200)
            for feed in feeds:
                xml = public.get(feed).content
                self.assertIn(b"<Price>130.75</Price>", xml)
                self.assertNotIn(b"NEVER-IN-FEED", xml)
                self.assertLess(xml.index(b"first.jpg"), xml.index(b"last.jpg"))
        prop.refresh_from_db()
        self.assertTrue(prop.export_to_cian and prop.export_to_domklik)

    def temp_media(self):
        from tempfile import TemporaryDirectory

        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return temp.name
