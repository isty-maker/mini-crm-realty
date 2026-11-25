from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

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
        self.assertEqual(self.client.post(edit, {**data, "price": "125.50"}).status_code, 302)
        inline = reverse("panel_update_price", args=[prop.pk])
        response = self.client.post(inline, {"price": "115,75"})
        self.assertEqual(response.json()["price"], "115.75")
        self.assertIn("История цены", response.json()["history_html"])

        changes = list(prop.price_history.values_list("previous_price", "new_price"))
        self.assertEqual(changes, [(Decimal("125.50"), Decimal("115.75")),
                                   (Decimal("100.25"), Decimal("125.50")),
                                   (None, Decimal("100.25"))])
        self.assertEqual(self.client.post(edit, {**data, "price": "115.75"}).status_code, 302)
        self.client.post(inline, {"price": "115.75"})
        self.assertEqual(prop.price_history.count(), 3)
        page = self.client.get(edit)
        self.assertContains(page, "Ступенчатый график")
        self.assertContains(page, "Исходная цена")

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
        executor.migrate([before])
        self.addCleanup(lambda: MigrationExecutor(connection).migrate([after]))
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
