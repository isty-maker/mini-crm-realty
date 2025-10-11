import json
import tempfile
from io import BytesIO

import pytest

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover - defensive guard
    pytest.skip(f"Pillow is required for photo tests ({exc})", allow_module_level=True)

try:  # pragma: no cover - optional dependency in stubbed environments
    from PIL import ImageOps
except Exception:  # pragma: no cover - pillow stub without ImageOps
    ImageOps = None  # type: ignore[assignment]


def _supports_rotation_api() -> bool:
    image_cls = getattr(Image, "Image", None)
    if image_cls is None:
        return False
    module_requirements = ("open", "new")
    if any(not hasattr(Image, attr) for attr in module_requirements):
        return False
    instance_requirements = ("rotate", "transpose", "convert", "getexif")
    if any(not hasattr(image_cls, attr) for attr in instance_requirements):
        return False
    if ImageOps is None:
        return False
    exif_transpose = getattr(ImageOps, "exif_transpose", None)
    return callable(exif_transpose)


_skip_rotate = pytest.mark.skipif(
    not _supports_rotation_api(),
    reason="rotate requires real Pillow support",
)

from core.models import Photo, Property


class PhotoManagementTests(TestCase):
    def _create_property(self):
        return Property.objects.create(title="Тест", address="Москва")

    @_skip_rotate
    def test_upload_rotates_by_exif_portrait(self):
        with tempfile.TemporaryDirectory() as tmpdir, self.settings(MEDIA_ROOT=tmpdir):
            prop = self._create_property()
            image = Image.new("RGB", (300, 200), "red")
            exif = image.getexif()
            exif[274] = 6
            buf = BytesIO()
            image.save(buf, format="JPEG", exif=exif.tobytes())
            upload = SimpleUploadedFile("portrait.jpg", buf.getvalue(), content_type="image/jpeg")

            response = self.client.post(
                reverse("panel_add_photo", args=[prop.id]),
                {"images": upload},
            )

            self.assertEqual(response.status_code, 302)
            photo = Photo.objects.get(property=prop)
            photo.image.open("rb")
            try:
                with Image.open(photo.image) as stored:
                    stored.load()
                    width, height = stored.size
            finally:
                photo.image.close()
            self.assertGreater(height, width)

    def test_bulk_delete_removes_many(self):
        with tempfile.TemporaryDirectory() as tmpdir, self.settings(MEDIA_ROOT=tmpdir):
            prop = self._create_property()
            p1 = Photo.objects.create(property=prop, full_url="https://example.com/1.jpg")
            p2 = Photo.objects.create(property=prop, full_url="https://example.com/2.jpg")
            p3 = Photo.objects.create(property=prop, full_url="https://example.com/3.jpg")

            response = self.client.post(
                reverse("panel_photos_bulk_delete"),
                {"property_id": prop.id, "ids[]": [p1.id, p2.id]},
            )

            self.assertEqual(response.status_code, 200)
            payload = json.loads(response.content.decode("utf-8"))
            self.assertTrue(payload.get("ok"))
            self.assertCountEqual(payload.get("deleted", []), [p1.id, p2.id])
            remaining = list(Photo.objects.filter(property=prop).values_list("id", flat=True))
            self.assertEqual(remaining, [p3.id])

    @_skip_rotate
    def test_rotate_endpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir, self.settings(MEDIA_ROOT=tmpdir):
            prop = self._create_property()
            base_image = Image.new("RGB", (300, 120), "blue")
            buf = BytesIO()
            base_image.save(buf, format="JPEG")
            photo = Photo.objects.create(property=prop)
            photo.image.save("rotate.jpg", ContentFile(buf.getvalue()), save=True)

            response = self.client.post(
                reverse("panel_photo_rotate", args=[photo.id]) + "?dir=right",
            )

            self.assertEqual(response.status_code, 200)
            payload = json.loads(response.content.decode("utf-8"))
            self.assertTrue(payload.get("ok"))

            photo.refresh_from_db()
            photo.image.open("rb")
            try:
                with Image.open(photo.image) as rotated:
                    rotated.load()
                    width, height = rotated.size
            finally:
                photo.image.close()
            self.assertLess(width, height)

    def test_scroll_restore_not_crash(self):
        with tempfile.TemporaryDirectory() as tmpdir, self.settings(MEDIA_ROOT=tmpdir):
            prop = self._create_property()
            response = self.client.post(reverse("panel_add_photo", args=[prop.id]), {})
            self.assertEqual(response.status_code, 302)
            self.assertIn(f"/panel/edit/{prop.id}/", response["Location"])
