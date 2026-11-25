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
from core.workspace_models import DriveFile, PropertyDocument, PropertyDocumentType, PropertyNote, PropertyWorkspace


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


class PrivateWorkspaceMigrationTests(TransactionTestCase):
    def test_both_supported_graphs_preserve_existing_data_and_price_history(self):
        alternate = getattr(settings, "MIGRATION_MODULES", {}).get("core") == "core.mig_current"
        before = ("core", "0002_price_history" if alternate else "0014_price_history")
        after = ("core", "0003_private_workspace" if alternate else "0015_private_workspace")
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
        executor.migrate([after])
        state = executor.loader.project_state([after]).apps
        current = state.get_model("core", "Property")
        migrated = current.objects.get(pk=prop.pk)
        self.assertEqual((migrated.price, migrated.is_archived, migrated.export_to_cian, migrated.export_to_domklik),
                         (100, True, True, False))
        self.assertEqual(list(state.get_model("core", "Photo").objects.filter(**{relation: prop.pk})
                              .values_list("pk", flat=True)), [second.pk, first.pk])
        self.assertFalse(state.get_model("core", "PropertyWorkspace").objects.exists())
        self.assertTrue(state.get_model("core", "PropertyDocumentType").objects.filter(slug="egrn").exists())
        current.objects.filter(pk=prop.pk).update(price=125)
        history = state.get_model("core", "PriceHistory")
        self.assertEqual(history.objects.get(property_id=prop.pk, kind="change").previous_price, 100)
