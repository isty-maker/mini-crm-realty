from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import Photo, Property


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
        with patch.object(Photo._meta.get_field("image").storage, "url",
                          return_value="https://example.invalid/cover.jpg"), self.assertNumQueries(3):
            page = self.client.get(reverse("panel_detail", args=[prop.pk]))
        self.assertEqual(page.context["photo_urls"], ["https://example.invalid/cover.jpg", "/media/photo.jpg"])
        for value in (
            "Тестовая улица, 12", "Продажа", "45,50 м²", "0 из 9",
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
        for value in ("Адрес не указан", "Цена не указана", "Фотографии не добавлены",
                      "Характеристики не заполнены", "Изменений цены пока нет",
                      "Приостановлена · архив"):
            self.assertContains(page, value)
        self.assertNotContains(page, "Планировка")
        self.assertNotContains(page, "Описание")
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
