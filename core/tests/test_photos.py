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


class MediaInfoHealthCheckTest(TestCase):
    def test_healthz_mediainfo(self):
        url = reverse("healthz_mediainfo")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("media_root", data)
        self.assertIn("writable", data)
        self.assertIn("exists_images_dir", data)
