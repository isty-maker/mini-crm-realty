from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from core.models import Photo, Property
from core.property_detail import editable_sections, save_section, section_version


class PropertyDetailTests(TestCase):
    def test_list_links_to_read_only_detail_and_detail_links_to_existing_form(self):
        prop = Property.objects.create(address="Тестовая улица, 12")
        detail = reverse("panel_detail", args=[prop.pk])
        edit = reverse("panel_edit", args=[prop.pk])
        panel = self.client.get(reverse("panel_list"))
        self.assertContains(panel, f'href="{detail}"', count=2)
        self.assertNotContains(panel, f'href="{edit}"')
        page = self.client.get(detail)
        self.assertContains(page, f'href="{edit}">Редактировать объявление</a>')
        self.assertTemplateUsed(self.client.get(edit), "core/panel_edit.html")
        self.assertEqual(self.client.head(detail).status_code, 200)
        self.assertEqual(self.client.post(detail, {"price": 999}).status_code, 405)
        self.assertEqual(self.client.get(reverse("panel_detail", args=[prop.pk + 1])).status_code, 404)
        prop.refresh_from_db()
        self.assertIsNone(prop.price)

    def test_detail_shows_existing_data_and_reuses_photo_and_history_order(self):
        prop = Property.objects.create(
            address="Тестовая улица, 12", category="flat", operation="sale",
            flat_type="apartment", description="Описание\nВторая строка\n<script>Не выполнять</script>",
            price="100.50", currency="eur", total_area="45.50",
            flat_rooms_count=2, floor_number=0, building_floors=9,
            layout_photo_url="https://example.invalid/plan.jpg", export_to_domklik=False,
            phone_number="PRIVATEPHONE", flat_number="PRIVATEFLAT",
        )
        Property.objects.filter(pk=prop.pk).update(price="105.75")
        Photo.objects.create(property=prop, full_url="/media/photo.jpg", sort=1)
        Photo.objects.create(property=prop, image="photos/cover.jpg", is_default=True, sort=10)
        Photo.objects.create(property=prop, full_url="javascript:alert(1)", sort=2)
        Photo.objects.create(property=prop, sort=3)
        detail = reverse("panel_detail", args=[prop.pk])
        with self.assertNumQueries(3):
            page = self.client.get(detail)
        self.assertNotContains(page, "<img")
        gallery_url = reverse("panel_property_gallery", args=[prop.pk])
        self.assertContains(page, f'href="{gallery_url}"')
        with patch.object(Photo._meta.get_field("image").storage, "url",
                          return_value="https://example.invalid/cover.jpg"):
            gallery = self.client.get(gallery_url)
        self.assertEqual(gallery.context["photo_urls"], ["https://example.invalid/cover.jpg", "/media/photo.jpg"])
        self.assertNotContains(gallery, "javascript:alert(1)")
        for value in (
            "Тестовая улица, 12", "Продажа", "45,50 м²", "<dt>Этаж</dt><dd>0</dd>",
            "105,75 <small>EUR</small>", "100,50 → 105,75", "Ступенчатый график",
            "Новокузнецк", "Планировка", "Описание<br>Вторая строка",
            "ЦИАН", "Домклик", "Включена", "Выключена", "&lt;script&gt;Не выполнять&lt;/script&gt;",
        ):
            self.assertContains(page, value)
        for value in ("PRIVATEPHONE", "PRIVATEFLAT", "javascript:alert(1)", "<script>Не выполнять</script>"):
            self.assertNotContains(page, value)

    def test_missing_values_and_archived_export_status(self):
        prop = Property.objects.create(is_archived=True, layout_photo_url="//unsafe.invalid/photo")
        url = reverse("panel_detail", args=[prop.pk])
        page = self.client.get(url)
        for value in ("Адрес не указан", "Цена не указана", "Характеристики не заполнены", "Изменений цены пока нет",
                      "Приостановлена · архив"):
            self.assertContains(page, value)
        self.assertNotContains(page, "Планировка")
        self.assertContains(page, "Описание не заполнено")
        self.assertNotContains(page, "Открыть галерею")
        Property.objects.filter(pk=prop.pk).update(price=0)
        self.assertContains(self.client.get(url), "0 <small>RUB</small>")

    def test_reads_do_not_change_existing_feeds(self):
        prop = Property.objects.create(address="Москва", category="flat", operation="sale",
                                       price=100, export_to_cian=True, export_to_domklik=True)
        detail = reverse("panel_detail", args=[prop.pk])
        with TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media), patch(
            "core.management.commands.generate_cian_feed.is_yandex_storage_configured", return_value=False
        ), patch("core.storage.is_yandex_storage_configured", return_value=False):
            for endpoint in ("export_cian", "export_domklik"):
                url = reverse(endpoint)
                before = self.client.get(url)
                self.assertEqual(before.status_code, 200)
                self.assertEqual(self.client.get(detail).status_code, 200)
                self.assertEqual(self.client.get(url).content, before.content)


class PropertySectionTests(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(
            address="Москва, Тестовая улица, 12", category="flat", operation="sale",
            flat_type="apartment", price=100, currency="rur", description="До изменения",
            total_area=45, living_area=30, phone_number="9001112233", export_to_domklik=True,
        )
        self.detail = reverse("panel_detail", args=[self.prop.pk])
        self.edit = reverse("panel_edit", args=[self.prop.pk])

    def open_editor(self, section, client=None):
        page = (client or self.client).get(self.detail, {"edit": section})
        self.assertEqual(page.status_code, 200)
        return page.context["panels"][section]

    def submit(self, section, panel, client=None, **changes):
        fields = {
            field.name: field.value() if field.value() is not None else ""
            for field in panel["form"]
        }
        url = reverse("panel_detail_section", args=[self.prop.pk, section])
        return (client or self.client).post(url, {**fields, "version": panel["version"], **changes})

    def test_saving_changes_full_editor_and_both_feeds_without_touching_other_values(self):
        first = Photo.objects.create(property=self.prop, full_url="https://example.invalid/one.jpg", sort=4)
        second = Photo.objects.create(property=self.prop, full_url="https://example.invalid/two.jpg",
                                      is_default=True, sort=10)
        with TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media), patch(
            "core.management.commands.generate_cian_feed.is_yandex_storage_configured", return_value=False
        ), patch("core.storage.is_yandex_storage_configured", return_value=False):
            endpoints = [reverse("export_cian"), reverse("export_domklik")]
            before = [self.client.get(url).content for url in endpoints]
            for xml in before:
                self.assertIn(b"<Price>100</Price>", xml)
                self.assertIn(b"<TotalArea>45</TotalArea>", xml)
            deal = self.open_editor("deal")
            self.assertRedirects(self.submit("deal", deal, price="125.50"),
                                 self.detail + "#section-deal", fetch_redirect_response=False)
            metrics = self.open_editor("metrics")
            self.assertEqual(self.submit("metrics", metrics, total_area="52.50").status_code, 302)
            self.assertEqual(self.submit("description", self.open_editor("description"),
                                         description="Новое описание").status_code, 302)
            for url in endpoints:
                xml = self.client.get(url).content
                self.assertIn(b"<Price>125.5</Price>", xml)
                self.assertIn(b"<TotalArea>52.5</TotalArea>", xml)
                self.assertIn("Новое описание".encode(), xml)
                self.assertLess(xml.index(b"two.jpg"), xml.index(b"one.jpg"))
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.living_area, 30)
        self.assertEqual(self.prop.phone_number, "9001112233")
        self.assertTrue(self.prop.export_to_cian)
        self.assertTrue(self.prop.export_to_domklik)
        self.assertEqual(list(self.prop.photos.values_list("pk", flat=True)), [second.pk, first.pk])
        self.assertEqual(self.prop.price_history.first().previous_price, Decimal(100))
        editor = self.client.get(self.edit).context["form"]
        self.assertEqual(editor["price"].value(), Decimal("125.50"))
        self.assertEqual(editor["total_area"].value(), Decimal("52.50"))
        self.assertEqual(editor["description"].value(), "Новое описание")

    def test_cancel_and_no_op_leave_state_and_price_history_untouched(self):
        original = self.prop.updated_at
        metrics = self.open_editor("metrics")
        self.assertContains(self.client.get(self.detail, {"edit": "metrics"}),
                            f'href="{self.detail}#section-metrics">Отмена</a>')
        self.client.get(self.detail)
        self.assertEqual(self.submit("metrics", metrics).status_code, 302)
        self.assertEqual(self.submit("deal", self.open_editor("deal"), price="100.00").status_code, 302)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.updated_at, original)
        self.assertEqual(self.prop.price_history.count(), 1)

    def test_invalid_values_and_non_allowed_fields_do_not_write(self):
        metrics = self.open_editor("metrics")
        for value in ("", "-1", "oops"):
            response = self.submit("metrics", metrics, total_area=value)
            self.assertEqual(response.status_code, 422)
            self.assertTrue(response.context["panels"]["metrics"]["form"].errors["total_area"])
        deal = self.open_editor("deal")
        for changes in ({"price": "-1"}, {"currency": "XYZ"}):
            self.assertEqual(self.submit("deal", deal, **changes).status_code, 422)
        self.assertEqual(self.submit("deal", deal, export_to_cian="false").status_code, 400)
        self.assertEqual(self.submit("deal", deal, version="tampered").status_code, 409)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.price, 100)
        self.assertEqual(self.prop.total_area, 45)
        self.assertTrue(self.prop.export_to_cian)

    def test_csrf_is_required_and_valid_token_allows_editing(self):
        client = Client(enforce_csrf_checks=True)
        panel = self.open_editor("address", client)
        self.assertEqual(self.submit("address", panel, client, address="Другой адрес").status_code, 403)
        response = self.submit("address", panel, client, address="Другой адрес",
                               csrfmiddlewaretoken=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 302)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.address, "Другой адрес")

    def test_stale_section_returns_409_but_other_section_can_still_save(self):
        metrics = self.open_editor("metrics")
        description = self.open_editor("description")
        Property.objects.filter(pk=self.prop.pk).update(total_area=60)
        self.assertEqual(self.submit("metrics", metrics, total_area="50").status_code, 409)
        self.assertEqual(self.submit("description", description, description="Новый текст").status_code, 302)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.total_area, 60)
        self.assertEqual(self.prop.description, "Новый текст")

    def test_compare_and_swap_rejects_changes_after_object_was_read(self):
        stale = Property.objects.get(pk=self.prop.pk)
        section = editable_sections(stale)["deal"]
        version = section_version(stale, section)
        Property.objects.filter(pk=self.prop.pk).update(price=150)
        self.assertFalse(save_section(stale, section, version, {"price": Decimal(120)}))
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.price, 150)
        self.assertEqual(self.prop.price_history.count(), 2)
