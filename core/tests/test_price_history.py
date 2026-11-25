from datetime import datetime, timezone as utc_timezone
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from core.models import PriceHistory, Property


class PriceHistoryTests(TestCase):
    def test_create_and_edit_in_panel_and_inline(self):
        data = {"title": "Тестовый объект", "address": "Тестовая улица", "category": "flat",
                "operation": "sale", "price": "100.25", "currency": "rur",
                "flat_type": "apartment", "total_area": "50"}
        self.assertEqual(self.client.post(reverse("panel_create"), data).status_code, 302)
        prop = Property.objects.get()
        origin = prop.price_history.get()
        self.assertEqual(origin.kind, PriceHistory.Kind.INITIAL)
        self.assertEqual(origin.new_price, Decimal("100.25"))

        edit = reverse("panel_edit", args=[prop.pk])
        self.assertEqual(self.client.post(edit, {**data, "price": "125.50", "edit_version": self.client.get(edit).context["edit_version"]}).status_code, 302)
        inline = reverse("panel_update_price", args=[prop.pk])
        response = self.client.post(inline, {"price": "115,75"})
        self.assertEqual(response.json()["price"], "115.75")
        self.assertIn("История цены", response.json()["history_html"])

        changes = list(prop.price_history.values_list("previous_price", "new_price"))
        self.assertEqual(changes, [(Decimal("125.50"), Decimal("115.75")),
                                   (Decimal("100.25"), Decimal("125.50")),
                                   (None, Decimal("100.25"))])
        self.assertEqual(self.client.post(edit, {**data, "price": "115.75", "edit_version": self.client.get(edit).context["edit_version"]}).status_code, 302)
        self.client.post(inline, {"price": "115.75"})
        self.assertEqual(prop.price_history.count(), 3)
        page = self.client.get(edit)
        self.assertContains(page, "Ступенчатый график")
        self.assertContains(page, "Исходная цена")

    def test_panel_history_uses_novokuznetsk_across_utc_midnight(self):
        prop = Property.objects.create(category="flat", operation="sale", price=100)
        Property.objects.filter(pk=prop.pk).update(price=200)
        prop.price_history.filter(kind=PriceHistory.Kind.INITIAL).update(
            recorded_at=datetime(2026, 11, 25, 16, 0, tzinfo=utc_timezone.utc)
        )
        prop.price_history.filter(kind=PriceHistory.Kind.CHANGE).update(
            recorded_at=datetime(2026, 11, 25, 21, 5, 6, tzinfo=utc_timezone.utc)
        )
        with timezone.override("UTC"):
            panel = self.client.get(reverse("panel_list"))
            edit = self.client.get(reverse("panel_edit", args=[prop.pk]))
            inline = self.client.post(reverse("panel_update_price", args=[prop.pk]), {"price": "200"})
        expected = "2026-11-26T04:05:06+07:00"
        for response in (panel, edit):
            self.assertContains(response, f'datetime="{expected}"')
            self.assertContains(response, "26.11.2026 04:05:06")
        self.assertContains(panel, f'datetime="{expected}">26.11.26</time>')
        self.assertContains(edit, "<figcaption>25.11.2026 23:00:00 — 26.11.2026 04:05:06</figcaption>")
        self.assertIn(f'datetime="{expected}"', inline.json()["history_html"])

    def test_latest_migrated_schema_records_inserts_and_price_updates(self):
        # A future SQLite table rebuild can silently drop either trigger.
        prop = Property.objects.create(price=100)
        Property.objects.filter(pk=prop.pk).update(price=125)
        self.assertEqual(
            list(prop.price_history.values_list("kind", "previous_price", "new_price")),
            [(PriceHistory.Kind.CHANGE, Decimal(100), Decimal(125)),
             (PriceHistory.Kind.INITIAL, None, Decimal(100))],
            "Preserve both SQLite price-history triggers when rebuilding core_property.",
        )

    def test_inline_can_save_from_fresh_panel_with_csrf_enabled(self):
        prop = Property.objects.create(price=100)
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("panel_list"))
        response = client.post(reverse("panel_update_price", args=[prop.pk]),
                               {"price": "200"}, headers={
                                   "X-CSRFToken": client.cookies["csrftoken"].value,
                               })
        self.assertEqual(response.status_code, 200)

    def test_empty_zero_and_invalid_price(self):
        prop = Property.objects.create()
        inline = reverse("panel_update_price", args=[prop.pk])
        self.assertIsNone(prop.price_history.get().new_price)
        self.assertEqual(self.client.post(inline, {"price": "0"}).json()["price_display"], "0")
        self.assertEqual(self.client.post(inline, {"price": ""}).json()["price"], "")
        for invalid in ("-1", "10000000000", "0.001"):
            self.assertEqual(self.client.post(inline, {"price": invalid}).status_code, 400)
        self.assertEqual(list(prop.price_history.values_list("previous_price", "new_price")),
                         [(Decimal(0), None), (None, Decimal(0)), (None, None)])

    def test_stale_writer_uses_current_stored_price_and_rollback_covers_history(self):
        prop = Property.objects.create(price=100)
        stale = Property.objects.get(pk=prop.pk)
        Property.objects.filter(pk=prop.pk).update(price=200)
        stale.price = 300
        stale.save(update_fields=["price"])
        self.assertEqual(stale.price_history.first().previous_price, Decimal(200))
        with self.assertRaises(RuntimeError), transaction.atomic():
            Property.objects.filter(pk=prop.pk).update(price=400)
            raise RuntimeError("abort")
        prop.refresh_from_db()
        self.assertEqual(prop.price, Decimal(300))
        self.assertEqual(prop.price_history.first().new_price, Decimal(300))
        self.assertEqual(prop.price_history.count(), 3)

    def test_list_limits_changes_per_property_and_loads_them_in_three_queries(self):
        Property.objects.create(price=100)
        with self.assertNumQueries(3):
            self.assertEqual(self.client.get(reverse("panel_list")).status_code, 200)
        for _ in range(3):
            prop = Property.objects.create(price=100)
            for price in range(101, 110):
                Property.objects.filter(pk=prop.pk).update(price=price)
        with self.assertNumQueries(3):
            page = self.client.get(reverse("panel_list"))
        for row in page.context["rows"]:
            if row["id"] == prop.pk:
                self.assertEqual([entry.new_price for entry in row["price_changes"]],
                                 [109, 108, 107, 106, 105])
                self.assertEqual(row["price_origin"].new_price, Decimal(100))

    def test_feeds_depend_on_current_values_only(self):
        prop = Property.objects.create(title="Тест", address="Москва", category="flat",
                                       operation="sale", price=100, export_to_cian=True,
                                       export_to_domklik=True)
        with TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media), patch(
            "core.management.commands.generate_cian_feed.is_yandex_storage_configured", return_value=False
        ), patch("core.storage.is_yandex_storage_configured", return_value=False):
            for endpoint in ("export_cian", "export_domklik"):
                url = reverse(endpoint)
                before = self.client.get(url)
                self.assertEqual(before.status_code, 200)
                Property.objects.filter(pk=prop.pk).update(price=200)
                Property.objects.filter(pk=prop.pk).update(price=100)
                self.assertEqual(self.client.get(url).content, before.content)


class PriceHistoryMigrationTests(TransactionTestCase):
    def test_snapshot_preserves_existing_properties_and_captures_future_changes(self):
        alternate = getattr(settings, "MIGRATION_MODULES", {}).get("core") == "core.mig_current"
        before = ("core", "0001_initial" if alternate else "0013_merge_20260927_1839")
        after = ("core", "0002_price_history" if alternate else "0014_price_history")
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        executor.migrate([before])
        old = executor.loader.project_state([before]).apps.get_model("core", "Property")
        existing = [old.objects.create(external_id=f"synthetic-{i}", price=price)
                    for i, price in enumerate((Decimal("14.25"), None, Decimal(0)))]
        executor = MigrationExecutor(connection)
        executor.migrate([after])
        apps = executor.loader.project_state([after]).apps
        history = apps.get_model("core", "PriceHistory")
        current = apps.get_model("core", "Property")
        for obj in existing:
            migrated = current.objects.get(pk=obj.pk)
            origin = history.objects.get(property_id=obj.pk)
            self.assertEqual(migrated.price, obj.price)
            self.assertEqual(migrated.created_at, obj.created_at)
            self.assertEqual(origin.kind, "baseline")
            self.assertEqual(origin.new_price, obj.price)
        current.objects.filter(pk=existing[0].pk).update(price=15)
        self.assertEqual(history.objects.get(kind="change").previous_price, Decimal("14.25"))
