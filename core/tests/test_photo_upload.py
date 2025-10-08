import io
from typing import Iterable

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Photo, Property

try:  # pragma: no cover - fallback when Pillow missing in environment
    from PIL import Image

    PIL_AVAILABLE = True
except Exception:  # pragma: no cover - allow skipping when Pillow absent
    PIL_AVAILABLE = False


def _img_bytes(fmt: str = "JPEG", size=(32, 24), color=(10, 20, 30)) -> bytes:
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow not available in test environment")
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class PhotoUploadTest(TestCase):
    def setUp(self) -> None:
        self.prop = Property.objects.create(title="Test", address="Addr")

    def _post_image(self, payload: bytes, name: str, content_type: str, follow: bool = False):
        upload = SimpleUploadedFile(name, payload, content_type=content_type)
        return self.client.post(
            reverse("panel_add_photo", args=[self.prop.id]),
            data={"image": upload},
            follow=follow,
        )

    def _messages(self, response) -> Iterable[str]:
        return [m.message for m in get_messages(response.wsgi_request)]

    def test_upload_valid_jpeg_ok(self):
        if not PIL_AVAILABLE:
            self.skipTest("Pillow not available")
        data = _img_bytes("JPEG")
        resp = self._post_image(data, "photo.jpg", "image/jpeg")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("Фото добавлено.", list(self._messages(resp)))
        self.assertTrue(Photo.objects.filter(property=self.prop).exists())

    def test_upload_valid_png_ok(self):
        if not PIL_AVAILABLE:
            self.skipTest("Pillow not available")
        data = _img_bytes("PNG")
        resp = self._post_image(data, "photo.png", "image/png")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Photo.objects.filter(property=self.prop).exists())

    def test_upload_invalid_file_error(self):
        resp = self._post_image(b"not-an-image", "bad.jpg", "image/jpeg", follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Неподдерживаемый формат или повреждённое изображение.", resp.content.decode("utf-8"))
        self.assertFalse(Photo.objects.filter(property=self.prop).exists())
