from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
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
            "Тестовая улица, 12", "Продажа", "45,50 м²", "<dt>Этаж</dt><dd>0/9</dd>",
            "105,75 <small>EUR</small>", "100,50 → 105,75", "Ступенчатый график",
            "Новокузнецк", "Планировка", "Описание<br>Вторая строка",
            "ЦИАН · вкл.", "Домклик · выкл.", "Публикация площадкой не подтверждена", "&lt;script&gt;Не выполнять&lt;/script&gt;",
        ):
            self.assertContains(page, value)
        for value in ("PRIVATEPHONE", "PRIVATEFLAT", "javascript:alert(1)", "<script>Не выполнять</script>"):
            self.assertNotContains(page, value)

    def test_missing_values_and_archived_export_status(self):
        prop = Property.objects.create(is_archived=True, layout_photo_url="//unsafe.invalid/photo")
        url = reverse("panel_detail", args=[prop.pk])
        page = self.client.get(url)
        for value in ("Адрес не указан", "Цена не указана", "Характеристики не заполнены", "Изменений цены пока нет",
                      "Выгрузка приостановлена для архивного объекта"):
            self.assertContains(page, value)
        self.assertContains(page, "Планировка · Не указана")
        self.assertContains(page, "Описание не заполнено")
        self.assertNotContains(page, "Фото (")
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
        self.employee = get_user_model().objects.create_user(username="test-employee", is_staff=True)
        self.client.force_login(self.employee)
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
        client.force_login(self.employee)
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


    def test_new_writes_and_private_fields_require_staff(self):
        Property.objects.filter(pk=self.prop.pk).update(cadastral_number="PRIVATE-CAD", flat_number="PRIVATE-APT",
                                                        furnishing_details="PRIVATE-FURNISHING")
        anonymous = Client()
        for url in (self.detail,):
            page = anonymous.get(url, {"edit": "deal"})
            for marker in ("PRIVATE-CAD", "PRIVATE-APT", "PRIVATE-FURNISHING", 'name="from_card"'):
                if marker != "PRIVATE-FURNISHING" or url == self.detail:
                    self.assertNotContains(page, marker)
        panel = self.open_editor("deal")
        self.assertEqual(self.submit("deal", panel, anonymous, price="900").status_code, 403)
        toggle = reverse("panel_toggle_export_cian", args=[self.prop.pk])
        self.assertEqual(anonymous.post(toggle, {"from_card": "1", "version": "x"}).status_code, 403)
        self.assertContains(self.client.get(self.detail), "PRIVATE-CAD")
        self.assertContains(self.client.get(self.detail), "PRIVATE-APT")
        self.assertIn("no-store", self.client.get(self.detail).headers["Cache-Control"])

    def test_legacy_multipart_create_and_partial_edit_keep_listing_identifiers(self):
        client = Client(enforce_csrf_checks=True)
        create = reverse("panel_create")
        client.get(create)
        csrf = client.cookies["csrftoken"].value
        fields = {"category": "flat", "operation": "sale", "flat_type": "apartment",
                  "currency": "rur", "total_area": "43.25", "cadastral_number": "SYNTHETIC-ID",
                  "flat_number": "TEST-7", "export_to_cian": "on", "csrfmiddlewaretoken": csrf}
        response = client.post(create, fields)
        self.assertEqual(response.status_code, 302)
        prop = Property.objects.get(cadastral_number="SYNTHETIC-ID")
        url = reverse("panel_edit", args=[prop.pk])
        response = client.post(url, {"csrfmiddlewaretoken": csrf, "description": "Синтетическое описание"})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        prop.refresh_from_db()
        self.assertEqual(prop.flat_number, "TEST-7")
        self.assertTrue(prop.export_to_cian)
        self.assertFalse(prop.export_to_domklik)
        self.assertEqual(client.post(url, {"description": "Без CSRF"}).status_code, 403)
        form = client.get(url)
        self.assertContains(form, 'name="edit_version"')
        bad = client.post(url, {"csrfmiddlewaretoken": csrf, "edit_version": form.context["edit_version"], "total_area": ""})
        self.assertEqual(bad.status_code, 200)
        self.assertTrue(bad.context["form"].errors["total_area"])
        response = client.post(url, {"csrfmiddlewaretoken": csrf, "edit_version": form.context["edit_version"],
                                     "export_to_cian": ["false", "on"], "export_to_domklik": "false",
                                     "cadastral_number": "SYNTHETIC-CHANGED"})
        self.assertEqual(response.status_code, 302)
        prop.refresh_from_db()
        self.assertEqual(prop.cadastral_number, "SYNTHETIC-CHANGED")
        self.assertTrue(prop.export_to_cian)
        fresh = client.get(url)
        unchecked = client.post(url, {"csrfmiddlewaretoken": csrf, "edit_version": fresh.context["edit_version"],
                                      "export_to_cian": "false", "flat_number": ""}, follow=True)
        self.assertRedirects(unchecked, url)
        prop.refresh_from_db()
        self.assertFalse(prop.export_to_cian)
        self.assertFalse(prop.export_to_domklik)
        self.assertFalse(prop.flat_number)
        self.assertEqual(prop.description, "Синтетическое описание")
        self.assertEqual(prop.cadastral_number, "SYNTHETIC-CHANGED")

    def test_full_editor_detects_card_update_and_preserves_draft(self):
        opened = self.client.get(self.edit).context["edit_version"]
        self.assertEqual(self.submit("deal", self.open_editor("deal"), price="130").status_code, 302)
        stale = self.client.post(self.edit, {"edit_version": opened, "price": "100", "description": "Ввод из старой вкладки"})
        self.assertEqual(stale.status_code, 409)
        self.assertContains(stale, "Ввод из старой вкладки", status_code=409)
        self.assertContains(stale, "130", status_code=409)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.price, 130)
        self.assertEqual(self.prop.description, "До изменения")

    def test_full_editor_changes_only_submitted_fields_and_no_op_has_no_history(self):
        opened = self.client.get(self.edit).context["edit_version"]
        response = self.client.post(self.edit, {"edit_version": opened, "description": "Новый текст", "price": "100"})
        self.assertEqual(response.status_code, 302, response.context["form"].errors if response.context else "")
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.description, "Новый текст")
        self.assertEqual(self.prop.living_area, 30)
        self.assertTrue(self.prop.export_to_cian)
        self.assertTrue(self.prop.export_to_domklik)
        self.assertEqual(self.prop.price_history.count(), 1)

    def test_full_editor_does_not_rewrite_unedited_textarea_line_endings(self):
        Property.objects.filter(pk=self.prop.pk).update(description="Первая строка\nВторая строка")
        opened = self.client.get(self.edit).context["edit_version"]
        response = self.client.post(self.edit, {"edit_version": opened, "price": 120,
                                                "description": "Первая строка\r\nВторая строка"})
        self.assertEqual(response.status_code, 302)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.description, "Первая строка\nВторая строка")
        self.assertEqual(self.prop.price, 120)

    def test_full_editor_change_invalidates_card_and_quick_versions(self):
        listing = self.client.get(reverse("panel_list")).context["rows"][0]
        opened = self.client.get(self.edit).context["edit_version"]
        deal = self.open_editor("deal")
        self.assertEqual(self.client.post(self.edit, {"edit_version": opened, "price": 150,
                                                     "export_to_cian": "false"}).status_code, 302)
        self.assertEqual(self.submit("deal", deal, price=160).status_code, 409)
        price_url = reverse("panel_update_price", args=[self.prop.pk])
        result = self.client.post(price_url, {"price": 165, "version": listing["price_version"]})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json()["current"], "150")
        toggle = reverse("panel_toggle_export_cian", args=[self.prop.pk])
        self.assertEqual(self.client.post(toggle, {"version": listing["cian_version"]}).status_code, 409)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.price, 150)
        self.assertFalse(self.prop.export_to_cian)
        self.assertTrue(self.prop.export_to_domklik)

    def test_two_full_editors_and_stale_archive_cannot_overwrite(self):
        opened = self.client.get(self.edit).context["edit_version"]
        row = self.client.get(reverse("panel_list")).context["rows"][0]
        self.assertEqual(self.client.post(self.edit, {"edit_version": opened, "is_archived": "on",
                                                     "status": "archived"}).status_code, 302)
        stale = self.client.post(self.edit, {"edit_version": opened, "price": 140})
        self.assertEqual(stale.status_code, 409)
        archive = reverse("panel_toggle_archive", args=[self.prop.pk])
        self.assertEqual(self.client.post(archive, {"version": row["archive_version"]}).status_code, 409)
        self.prop.refresh_from_db()
        self.assertTrue(self.prop.is_archived)
        self.assertEqual(self.prop.price, 100)

    def test_quick_price_and_export_changes_invalidate_full_editor(self):
        edit = self.client.get(self.edit)
        row = self.client.get(reverse("panel_list")).context["rows"][0]
        self.assertEqual(self.client.post(reverse("panel_update_price", args=[self.prop.pk]),
                         {"price": 160, "version": row["price_version"]}).status_code, 200)
        stale = self.client.post(self.edit, {"edit_version": edit.context["edit_version"], "price": 100})
        self.assertEqual(stale.status_code, 409)
        edit = self.client.get(self.edit)
        card = self.client.get(self.detail)
        self.assertEqual(self.client.post(reverse("panel_toggle_export_dom", args=[self.prop.pk]), {
            "from_card": "1", "version": card.context["dom_version"],
        }).status_code, 302)
        stale = self.client.post(self.edit, {"edit_version": edit.context["edit_version"], "export_to_domklik": "on"})
        self.assertEqual(stale.status_code, 409)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.price, 160)
        self.assertFalse(self.prop.export_to_domklik)
        self.assertTrue(self.prop.export_to_cian)

    def test_card_export_chip_renders_a_csrf_token_and_requires_it(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.employee)
        page = client.get(self.detail)
        self.assertContains(page, 'name="csrfmiddlewaretoken"', count=2)
        url = reverse("panel_toggle_export_cian", args=[self.prop.pk])
        data = {"from_card": "1", "version": page.context["cian_version"]}
        self.assertEqual(client.post(url, data).status_code, 403)
        data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        self.assertEqual(client.post(url, data).status_code, 302)

    def test_rooms_mapping_stays_distinct_in_both_feeds(self):
        Property.objects.filter(pk=self.prop.pk).update(rooms=2, flat_rooms_count=3)
        self.assertContains(self.client.get(self.detail), "3-комнатная квартира · Продажа")
        with TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media), patch(
            "core.management.commands.generate_cian_feed.is_yandex_storage_configured", return_value=False
        ), patch("core.storage.is_yandex_storage_configured", return_value=False):
            for endpoint in ("export_cian", "export_domklik"):
                xml = self.client.get(reverse(endpoint)).content
                self.assertIn(b"<FlatRoomsCount>3</FlatRoomsCount>", xml)
                self.assertIn(b"<RoomsCount>2</RoomsCount>", xml)
        metrics = self.open_editor("metrics")
        self.assertEqual(self.submit("metrics", metrics, flat_rooms_count=4).status_code, 302)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.rooms, 2)

    def test_applicable_fields_change_with_category(self):
        cases = {
            "flat": ("flat_rooms_count", "room_area"),
            "room": ("room_area", "land_area"),
            "house": ("bedrooms_count", "floor_number"),
            "land": ("land_area", "total_area"),
            "commercial": ("power", "flat_rooms_count"),
        }
        for category, (present, absent) in cases.items():
            with self.subTest(category=category):
                self.prop.category = category
                fields = {name for section in editable_sections(self.prop).values() for name in section.fields}
                self.assertIn(present, fields)
                self.assertNotIn(absent, fields)
