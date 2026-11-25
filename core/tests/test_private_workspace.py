from datetime import date
from xml.etree.ElementTree import fromstring

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from core.cian import build_cian_feed
from core.models import Property
from core.workspace_models import DriveFile, PropertyDocument, PropertyDocumentType, PropertyNote, PropertyOwner, PropertyWorkspace


class PrivateWorkspaceTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(category="flat", operation="sale", price=100, total_area=50)
        self.workspace = PropertyWorkspace.objects.create(property=self.property)
        self.staff = get_user_model().objects.create_superuser(username="synthetic-staff", password="test-password-fixture")

    def test_validation_independently_checks_source_document_dates_and_links(self):
        workspace = self.workspace
        workspace.encumbrances = workspace.Encumbrances.CLEAR
        with self.assertRaises(ValidationError):
            workspace.full_clean()
        workspace.encumbrance_source = "Синтетический источник"
        workspace.encumbrance_checked_on = date(2026, 1, 2)
        workspace.full_clean()
        other = PropertyWorkspace.objects.create(property=Property.objects.create())
        file = DriveFile.objects.create(workspace=other, file_id="fixture", name="Синтетический файл")
        document = PropertyDocument(workspace=workspace, document_type=PropertyDocumentType.objects.get(slug="egrn"),
                                    original=file, verification=PropertyDocument.Review.CHECKED)
        with self.assertRaises(ValidationError) as error:
            document.full_clean()
        self.assertIn("original", error.exception.message_dict)
        self.assertIn("checked_on", error.exception.message_dict)
        self.assertEqual(document.applicability, PropertyDocument.Applicability.UNKNOWN)
        self.assertEqual(document.availability, PropertyDocument.Availability.UNKNOWN)
        self.assertIsNone(document.document_date)

    def test_private_workspace_leaves_public_feeds_and_flags_unchanged(self):
        before = build_cian_feed([self.property]).xml
        self.workspace.work_status = PropertyWorkspace.WorkStatus.SOLD
        self.workspace.legal_comments = "SYNTHETIC-RESTRICTED"
        self.workspace.documented_area = 48
        self.workspace.documented_area_source = "Учебный документ"
        self.workspace.documented_area_checked_on = date(2026, 1, 2)
        self.workspace.full_clean()
        self.workspace.save()
        self.property.refresh_from_db()
        self.assertTrue(self.property.export_to_cian)
        self.assertFalse(self.property.is_archived)
        self.assertEqual(self.property.total_area, 50)
        after = build_cian_feed([self.property]).xml
        self.assertEqual(fromstring(before).tag, fromstring(after).tag)
        self.assertEqual(after, before)
        self.assertNotIn(b"SYNTHETIC-RESTRICTED", after)

    @override_settings(CRM_REQUIRE_STAFF_LOGIN=False)
    def test_private_admin_remains_closed_when_rollout_is_disabled(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("crm_workspace_admin:index")).status_code, 302)

    @override_settings(CRM_REQUIRE_STAFF_LOGIN=True)
    def test_staff_admin_can_save_note_with_real_author_and_nonstaff_cannot_enter(self):
        url = reverse("panel_private_record", args=[self.property.pk, "notes"])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(get_user_model().objects.create_user(username="ordinary-fixture"))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.staff)
        version = self.client.get(url).context["private_editor"]["version"]
        self.assertEqual(self.client.post(url, {"version": version, "text": "Учебная заметка"}).status_code, 302)
        admin_url = reverse("crm_workspace_admin:core_propertynote_add")
        self.assertEqual(self.client.get(admin_url).status_code, 403)
        note = PropertyNote.objects.get()
        self.assertEqual(note.author, self.staff)
        self.assertEqual(note.text, "Учебная заметка")


    @override_settings(CRM_REQUIRE_STAFF_LOGIN=False)
    def test_private_records_check_scope_and_stale_versions_even_in_transition(self):
        url = reverse("panel_private_record", args=[self.property.pk, "legal"])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.staff)
        version = self.client.get(url).context["private_editor"]["version"]
        self.assertEqual(self.client.post(url, {"version": version, "legal_comments": "Учебная проверка"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"version": version, "legal_comments": "Устарело"}).status_code, 409)
        other = PropertyWorkspace.objects.create(property=Property.objects.create())
        note = PropertyNote.objects.create(workspace=other, author=self.staff, text="Чужая заметка")
        foreign = reverse("panel_private_record", args=[self.property.pk, "notes", note.pk])
        self.assertEqual(self.client.get(foreign).status_code, 404)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.legal_comments, "Учебная проверка")
        change = self.property.staff_changes.get()
        self.assertEqual((change.actor, change.source, change.fields),
                         (self.staff, "card", ["legal_comments"]))

    def test_staff_summary_shows_unknown_documents_and_neutral_owner_warnings(self):
        self.client.force_login(self.staff)
        url = reverse("panel_detail", args=[self.property.pk])
        PropertyWorkspace.objects.filter(pk=self.workspace.pk).update(owner_count=2)
        PropertyOwner.objects.create(workspace=self.workspace, name="SYNTHETIC OWNER", share_numerator=1,
                                     share_denominator=2)
        page = self.client.get(url)
        for text in ("Выписка ЕГРН", "Согласие супруга", "Разрешение органов опеки", "Не выяснено · Не внесено",
                     "Список собственников: 1 из 2", "сумма отличается от целого"):
            self.assertContains(page, text)
        self.assertNotContains(page, '<details class="property-card" id="private-owners" open>')
        self.assertNotContains(page, "Выгрузка объявлений")
        self.assertIn("no-store", page["Cache-Control"])
        self.client.logout()
        self.assertNotContains(self.client.get(url), "SYNTHETIC OWNER")

    def test_retirement_requires_confirmation_scope_and_version_and_preserves_history(self):
        note = PropertyNote.objects.create(workspace=self.workspace, author=self.staff, text="Старая заметка")
        self.client.force_login(self.staff)
        url = reverse("panel_private_record", args=[self.property.pk, "notes", note.pk])
        old = self.client.get(url).context["private_editor"]["version"]
        self.assertEqual(self.client.post(url, {"version": old, "text": "Уточнение"}).status_code, 302)
        action = {"action": "retire", "version": old, "confirm": "on"}
        self.assertEqual(self.client.post(url, action).status_code, 409)
        fresh = self.client.get(url).context["private_editor"]["version"]
        self.assertEqual(self.client.post(url, {**action, "version": fresh, "confirm": ""}).status_code, 400)
        other = Property.objects.create()
        foreign = reverse("panel_private_record", args=[other.pk, "notes", note.pk])
        self.assertEqual(self.client.post(foreign, {**action, "version": fresh}).status_code, 404)
        self.assertEqual(self.client.post(url, {**action, "version": fresh}).status_code, 302)
        note.refresh_from_db()
        self.assertFalse(note.is_current)
        self.assertEqual(note.text, "Уточнение")
        self.assertNotContains(self.client.get(reverse("panel_detail", args=[self.property.pk])), "Уточнение")
        self.assertEqual(self.property.staff_changes.latest("pk").fields, ["is_current"])
        deleted = self.client.post(reverse("panel_delete", args=[self.property.pk]))
        self.assertEqual(deleted.status_code, 409)
        self.assertTrue(PropertyNote.objects.filter(pk=note.pk).exists())

    def test_document_state_and_file_retirement_are_validated(self):
        self.client.force_login(self.staff)
        file = DriveFile.objects.create(workspace=self.workspace, file_id="fixture-link", name="Тестовый файл")
        doc_type = PropertyDocumentType.objects.get(slug="egrn")
        created = reverse("panel_private_record", args=[self.property.pk, "documents"])
        page = self.client.get(created, {"type": "egrn"})
        self.assertEqual(page.context["private_editor"]["form"].initial["document_type"], doc_type.pk)
        invalid = self.client.post(created, {"version": page.context["private_editor"]["version"],
                                           "document_type": doc_type.pk, "availability": "missing",
                                           "verification": "checked", "checked_on": "2026-01-02"})
        self.assertContains(invalid, "Отсутствующий документ нельзя отметить проверенным", status_code=422)
        self.assertFalse(PropertyDocument.objects.exists())
        PropertyDocument.objects.create(workspace=self.workspace, document_type=doc_type, original=file)
        url = reverse("panel_private_record", args=[self.property.pk, "files", file.pk])
        version = self.client.get(url).context["private_editor"]["version"]
        blocked = self.client.post(url, {"version": version, "action": "retire", "confirm": "on"})
        self.assertContains(blocked, "Сначала измените ссылку", status_code=422)
        file.refresh_from_db()
        self.assertTrue(file.is_current)



class PrivateWorkspaceMigrationTests(TransactionTestCase):
    def test_both_supported_graphs_preserve_existing_data_and_price_history(self):
        alternate = getattr(settings, "MIGRATION_MODULES", {}).get("core") == "core.mig_current"
        before = ("core", "0002_price_history" if alternate else "0014_price_history")
        workspace_release = ("core", "0004_workspace_audit" if alternate else "0016_workspace_audit")
        after = ("core", "0008_align_listing_schema" if alternate else "0018_safe_workspace_audit_diff")
        executor = MigrationExecutor(connection)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(executor.loader.graph.leaf_nodes()))
        executor.migrate([before])
        state = executor.loader.project_state([before]).apps
        old_property = state.get_model("core", "Property")
        old_photo = state.get_model("core", "Photo")
        url_field = "url" if alternate else "full_url"
        relation = "prop_id" if alternate else "property_id"
        prop = old_property.objects.create(external_id="synthetic-property", price=100, is_archived=True,
                                           export_to_cian=True, export_to_domklik=False)
        first = old_photo.objects.create(**{relation: prop.pk, url_field: "https://example.invalid/one.jpg"})
        second = old_photo.objects.create(is_default=True, **{relation: prop.pk, url_field: "https://example.invalid/two.jpg"})
        executor = MigrationExecutor(connection)
        executor.migrate([workspace_release])
        state = executor.loader.project_state([workspace_release]).apps
        workspace = state.get_model("core", "PropertyWorkspace").objects.create(property_id=prop.pk)
        note = state.get_model("core", "PropertyNote").objects.create(workspace_id=workspace.pk, text="История")
        executor = MigrationExecutor(connection)
        executor.migrate([after])
        state = executor.loader.project_state([after]).apps
        self.assertTrue(state.get_model("core", "PropertyNote").objects.get(pk=note.pk).is_current)
        current = state.get_model("core", "Property")
        migrated = current.objects.get(pk=prop.pk)
        self.assertEqual((migrated.price, migrated.is_archived, migrated.export_to_cian, migrated.export_to_domklik),
                         (100, True, True, False))
        photos = state.get_model("core", "Photo").objects.filter(property_id=prop.pk)
        self.assertEqual(list(photos.values_list("pk", "full_url")), [
            (second.pk, "https://example.invalid/two.jpg"), (first.pk, "https://example.invalid/one.jpg"),
        ])
        self.assertEqual(Property.objects.get(pk=prop.pk).building_series, "")
        self.assertEqual(state.get_model("core", "PropertyWorkspace").objects.get(property_id=prop.pk).work_status, "unknown")
        self.assertTrue(state.get_model("core", "PropertyDocumentType").objects.filter(slug="egrn").exists())
        current.objects.filter(pk=prop.pk).update(price=125)
        history = state.get_model("core", "PriceHistory")
        self.assertEqual(history.objects.get(property_id=prop.pk, kind="change").previous_price, 100)
        if alternate:
            self.assertEqual(history.objects.filter(property_id=prop.pk).count(), 2)
            executor = MigrationExecutor(connection)
            executor.migrate([workspace_release])
            reverted = executor.loader.project_state([workspace_release]).apps
            reverted.get_model("core", "Property").objects.filter(pk=prop.pk).update(price=130)
            executor = MigrationExecutor(connection)
            executor.migrate([after])
            self.assertEqual(history.objects.filter(property_id=prop.pk, kind="change").count(), 2)
            self.assertEqual(Property.objects.get(pk=prop.pk).price, 130)
