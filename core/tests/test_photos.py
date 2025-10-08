import os
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from core.models import Photo, Property


def make_img_bytes(fmt="JPEG", w=3000, h=2000):
    img = Image.new("RGB", (w, h), (200, 200, 200))
    buf = BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf.read()


class PhotoUploadTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(title="Тест", address="Москва")
        self.upload_url = reverse("panel_add_photo", kwargs={"pk": self.prop.id})
        log_path = Path(settings.MEDIA_ROOT) / "logs" / "upload_errors.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")

    def _post_file(self, filename, content, content_type, **extra):
        file = SimpleUploadedFile(filename, content, content_type=content_type)
        payload = {"image": file, **extra}
        return self.client.post(self.upload_url, payload)

    def test_upload_creates_photo_for_allowed_formats(self):
        for fmt, ext, ctype in (
            ("JPEG", "jpg", "image/jpeg"),
            ("PNG", "png", "image/png"),
            ("WEBP", "webp", "image/webp"),
        ):
            with self.subTest(fmt=fmt):
                Photo.objects.all().delete()
                resp = self._post_file(
                    f"test.{ext}", make_img_bytes(fmt=fmt), ctype, is_default="on"
                )
                self.assertIn(resp.status_code, (302, 303))
                ph = Photo.objects.filter(property=self.prop).first()
                self.assertTrue(ph and ph.image)

    def test_upload_without_file_shows_message(self):
        resp = self.client.post(self.upload_url, {"is_default": "on"})
        self.assertIn(resp.status_code, (302, 303))
        msgs = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertIn("Не выбрано ни файла, ни URL.", msgs)
        self.assertFalse(Photo.objects.filter(property=self.prop).exists())

    def test_upload_heic_reports_error_and_logs(self):
        resp = self._post_file(
            "test.heic", b"fake", "image/heic", is_default="on"
        )
        self.assertIn(resp.status_code, (302, 303))
        msgs = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertIn(
            "HEIC/HEIF пока не поддерживается — сохраните как JPG/PNG/WebP.", msgs
        )
        self.assertFalse(Photo.objects.filter(property=self.prop).exists())
        import logging

        logger = logging.getLogger("upload")
        self.assertTrue(logger.handlers)
        for handler in logger.handlers:
            try:
                handler.flush()
            except Exception:
                pass
        log_path = Path(settings.MEDIA_ROOT) / "logs" / "upload_errors.log"
        self.assertTrue(log_path.exists())
        self.assertIn("HEIC/HEIF пока не поддерживается", log_path.read_text("utf-8"))

    def test_upload_invalid_image_reports_clear_error(self):
        resp = self._post_file("broken.jpg", b"notimage", "image/jpeg")
        self.assertIn(resp.status_code, (302, 303))
        msgs = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertIn("Неподдерживаемый формат или повреждённое изображение.", msgs)
        self.assertFalse(Photo.objects.filter(property=self.prop).exists())


class PhotoManagementTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(title="Test", address="Москва")
        self.upload_url = reverse("panel_add_photo", kwargs={"pk": self.prop.id})

    def _upload_photo(self, name="test.jpg"):
        file = SimpleUploadedFile(name, make_img_bytes(), content_type="image/jpeg")
        response = self.client.post(self.upload_url, {"image": file})
        self.assertIn(response.status_code, (302, 303))
        return Photo.objects.get(property=self.prop)

    def test_delete_photo_removes_file(self):
        photo = self._upload_photo()
        path = photo.image.path
        self.assertTrue(os.path.exists(path))

        url = reverse("panel_photo_delete", kwargs={"pk": photo.id})
        response = self.client.post(url)

        self.assertIn(response.status_code, (302, 303))
        self.assertFalse(Photo.objects.filter(id=photo.id).exists())
        self.assertFalse(os.path.exists(path))
        msgs = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Фото удалено.", msgs)

    def test_reorder_photos_updates_sort(self):
        p1 = Photo.objects.create(property=self.prop, full_url="http://example.com/1.jpg", sort=10)
        p2 = Photo.objects.create(property=self.prop, full_url="http://example.com/2.jpg", sort=20)
        p3 = Photo.objects.create(property=self.prop, full_url="http://example.com/3.jpg", sort=30)

        url = reverse("panel_photos_reorder", kwargs={"prop_id": self.prop.id})
        order = f"{p3.id},{p1.id},{p2.id}"
        response = self.client.post(url, {"order": order})

        self.assertIn(response.status_code, (302, 303))
        ordered_ids = list(
            Photo.objects.filter(property=self.prop)
            .order_by("sort")
            .values_list("id", flat=True)
        )
        self.assertEqual(ordered_ids, [p3.id, p1.id, p2.id])

        self.assertEqual(Photo.objects.get(id=p3.id).sort, 10)
        self.assertEqual(Photo.objects.get(id=p1.id).sort, 20)
        self.assertEqual(Photo.objects.get(id=p2.id).sort, 30)

        msgs = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Порядок фото сохранён.", msgs)

    def test_feed_uses_saved_order(self):
        prop = Property.objects.create(
            title="Feed", address="Москва", category="flat", operation="sale",
            external_id="AG-FEED", export_to_cian=True, total_area=42,
        )
        p1 = Photo.objects.create(property=prop, full_url="http://example.com/1.jpg", sort=20)
        p2 = Photo.objects.create(property=prop, full_url="http://example.com/2.jpg", sort=10)
        p3 = Photo.objects.create(
            property=prop,
            full_url="http://example.com/3.jpg",
            sort=30,
            is_default=True,
        )

        response = self.client.get(reverse("export_cian"))
        self.assertEqual(response.status_code, 200)

        root = ET.fromstring(response.content)
        target = None
        for obj in root.findall("Object"):
            if obj.findtext("ExternalId") == prop.external_id:
                target = obj
                break
        self.assertIsNotNone(target)
        photos_el = target.find("Photos")
        self.assertIsNotNone(photos_el)
        urls = [node.findtext("FullUrl") for node in photos_el.findall("PhotoSchema")]
        self.assertEqual(urls, [p3.full_url, p2.full_url, p1.full_url])


class MediaInfoHealthCheckTest(TestCase):
    def test_healthz_mediainfo(self):
        url = reverse("healthz_mediainfo")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("media_root", data)
        self.assertIn("writable", data)
        self.assertIn("exists_images_dir", data)
