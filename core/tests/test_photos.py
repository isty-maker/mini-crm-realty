import logging
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Photo, Property


def make_img_bytes():
    from PIL import Image
    from io import BytesIO

    img = Image.new("RGB", (600, 400), (200, 200, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


class PhotoUploadTest(TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.override = override_settings(MEDIA_ROOT=self.tmpdir)
        self.override.enable()
        self.prop = Property.objects.create(title="Тест", address="Москва")
        self.url = reverse("panel_add_photo", kwargs={"pk": self.prop.id})
        self.logger = logging.getLogger("upload")
        self.original_handlers = list(self.logger.handlers)
        self.original_level = self.logger.level
        self.original_propagate = self.logger.propagate
        for handler in self.original_handlers:
            self.logger.removeHandler(handler)
        self.log_path = self.tmpdir / "logs" / "upload_errors.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.handler = logging.FileHandler(self.log_path, encoding="utf-8")
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

    def tearDown(self):
        self.handler.flush()
        self.logger.removeHandler(self.handler)
        self.handler.close()
        for handler in self.original_handlers:
            self.logger.addHandler(handler)
        self.logger.setLevel(self.original_level)
        self.logger.propagate = self.original_propagate
        self.override.disable()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_upload_valid_image_creates_photo(self):
        file = SimpleUploadedFile("photo.jpg", make_img_bytes(), content_type="image/jpeg")
        resp = self.client.post(self.url, {"image": file})
        self.assertEqual(resp.status_code, 302)
        ph = Photo.objects.filter(property=self.prop).first()
        self.assertIsNotNone(ph)
        self.assertTrue(ph.image)
        self.assertTrue(ph.image.storage.exists(ph.image.name))

    def test_upload_without_file_or_url_does_not_crash(self):
        resp = self.client.post(self.url, {})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Photo.objects.filter(property=self.prop).count(), 0)

    def test_upload_invalid_file_logs_error(self):
        bad = SimpleUploadedFile("bad.jpg", b"not-an-image", content_type="image/jpeg")
        resp = self.client.post(self.url, {"image": bad})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Photo.objects.filter(property=self.prop).count(), 0)
        self.handler.flush()
        self.assertTrue(self.log_path.exists())
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("upload failed", content)
