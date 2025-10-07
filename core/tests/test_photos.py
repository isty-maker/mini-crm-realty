from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from core.models import Property, Photo
from PIL import Image
from io import BytesIO


def dummy_image_bytes(w=3000, h=2000, color=(200, 200, 200)):
    img = Image.new("RGB", (w, h), color)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()


class PhotoFlowTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(title="Тест", address="Москва")

    def test_upload_and_compress(self):
        content = dummy_image_bytes()
        file = SimpleUploadedFile("big.jpg", content, content_type="image/jpeg")
        url = reverse("panel_add_photo", kwargs={"pk": self.prop.id})
        resp = self.client.post(url, {"is_default": "on"}, FILES={"image": file})
        self.assertIn(resp.status_code, (302, 303))
        ph = Photo.objects.filter(prop=self.prop).first()
        self.assertTrue(ph and ph.image)
        from PIL import Image as PILImage
        im = PILImage.open(ph.image.path)
        self.assertLessEqual(max(im.size), 2560)

    def test_make_main_toggle(self):
        p1 = Photo.objects.create(prop=self.prop, is_default=True)
        p2 = Photo.objects.create(prop=self.prop)
        url = reverse("panel_toggle_main", kwargs={"photo_id": p2.id})
        self.client.get(url)
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertFalse(p1.is_default)
        self.assertTrue(p2.is_default)
