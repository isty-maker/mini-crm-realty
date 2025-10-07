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
        ph = Photo.objects.filter(prop=self.prop).first()
        self.assertTrue(ph and ph.image)
        from PIL import Image as PILImage

        im = PILImage.open(ph.image.path)
        self.assertLessEqual(max(im.size), 2560)
