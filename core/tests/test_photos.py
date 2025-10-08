from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from core.models import Property, Photo
from PIL import Image
from io import BytesIO


def make_img_bytes(w=3000, h=2000):
    img = Image.new("RGB", (w, h), (200, 200, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


class PhotoUploadTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(title="Тест", address="Москва")

    def test_upload_and_compress(self):
        file = SimpleUploadedFile("big.jpg", make_img_bytes(), content_type="image/jpeg")
        url = reverse("panel_add_photo", kwargs={"pk": self.prop.id})
        resp = self.client.post(url, {"is_default": "on", "image": file})
        self.assertIn(resp.status_code, (302, 303))
        ph = Photo.objects.filter(property=self.prop).first()
        self.assertTrue(ph and ph.image)
        from PIL import Image as PILImage

        im = PILImage.open(ph.image.path)
        self.assertLessEqual(max(im.size), 2560)

    def test_upload_without_file_shows_message(self):
        url = reverse("panel_add_photo", kwargs={"pk": self.prop.id})
        resp = self.client.post(url, {"is_default": "on"})
        self.assertIn(resp.status_code, (302, 303))
        msgs = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertIn("Не выбрано ни файла, ни URL.", msgs)
        self.assertFalse(Photo.objects.filter(property=self.prop).exists())

    def test_upload_invalid_image_shows_message(self):
        url = reverse("panel_add_photo", kwargs={"pk": self.prop.id})
        bad_file = SimpleUploadedFile("broken.jpg", b"notimage", content_type="image/jpeg")
        resp = self.client.post(url, {"image": bad_file})
        self.assertIn(resp.status_code, (302, 303))
        msgs = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertIn("Не удалось загрузить фото", msgs)
        self.assertFalse(Photo.objects.filter(property=self.prop).exists())
