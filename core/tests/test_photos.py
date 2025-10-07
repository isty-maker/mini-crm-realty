import base64
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Photo, Property


class PanelPhotoUploadTest(TestCase):
    def tearDown(self):
        for photo in Photo.objects.all():
            name = self._storage_name_from_url(photo.full_url)
            if name and default_storage.exists(name):
                default_storage.delete(name)

    def _storage_name_from_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        if parsed.scheme:
            path = parsed.path
        else:
            path = parsed.path or url
        media_url = settings.MEDIA_URL or ""
        if media_url and path.startswith(media_url):
            path = path[len(media_url) :]
        return path.lstrip("/")

    def _make_image_file(self):
        raw = base64.b64decode(
            b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAn8B9sJr4usAAAAASUVORK5CYII="
        )
        return SimpleUploadedFile("test.png", raw, content_type="image/png")

    def test_upload_and_compress(self):
        prop = Property.objects.create(title="Тестовый объект", address="Москва")
        url = reverse("panel_add_photo", args=[prop.pk])
        file = self._make_image_file()

        resp = self.client.post(url, {"is_default": "on", "image": file})

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(prop.photos.count(), 1)

        photo = prop.photos.first()
        self.assertTrue(photo.full_url)

        name = self._storage_name_from_url(photo.full_url)
        self.assertTrue(name)
        self.assertTrue(default_storage.exists(name))

        self.assertGreater(default_storage.size(name), 0)
