import io
import os

from django.test import TestCase
from django.urls import reverse

from core.models import Photo, Property
from core.utils import image_pipeline

Image = image_pipeline.Image
PIL_OK = not hasattr(Image, "__dataclass_fields__")


def _mk_img(fmt="JPEG", size=(3000, 2000), color=(40, 80, 120), quality=95, noise=False):
    if not PIL_OK:
        raise RuntimeError("Pillow not available")
    if noise:
        im = Image.effect_noise(size, 64).convert("RGB")
    else:
        im = Image.new("RGB", size, color)
    buf = io.BytesIO()
    if fmt == "JPEG":
        im.save(buf, format="JPEG", quality=quality, optimize=True)
    else:
        im.save(buf, format=fmt)
    return buf.getvalue()


class PhotoUploadCompressAlwaysTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(title="T", address="A")

    def test_jpeg_is_compressed(self):
        if not PIL_OK:
            self.skipTest("Pillow not available")
        src = _mk_img("JPEG", (3000, 2000), quality=95)
        f = io.BytesIO(src)
        f.name = "big.jpg"
        resp = self.client.post(
            reverse("panel_add_photo", args=[self.prop.id]),
            data={"image": f},
            format="multipart",
        )
        self.assertIn(resp.status_code, (302, 200))
        ph = Photo.objects.filter(property=self.prop).order_by("-id").first()
        self.assertIsNotNone(ph)
        saved = os.path.getsize(ph.image.path)
        self.assertLess(
            saved,
            int(len(src) * 0.8),
            f"expected compressed <80%, got {saved} vs {len(src)}",
        )
        with Image.open(ph.image.path) as im2:
            self.assertEqual(im2.format, "JPEG")

    def test_png_converts_and_compresses(self):
        if not PIL_OK:
            self.skipTest("Pillow not available")
        src = _mk_img("PNG", (3000, 2000), noise=True)
        f = io.BytesIO(src)
        f.name = "big.png"
        resp = self.client.post(
            reverse("panel_add_photo", args=[self.prop.id]),
            data={"image": f},
            format="multipart",
        )
        self.assertIn(resp.status_code, (302, 200))
        ph = Photo.objects.filter(property=self.prop).order_by("-id").first()
        self.assertIsNotNone(ph)
        saved = os.path.getsize(ph.image.path)
        self.assertLess(saved, int(len(src) * 0.7))
        with Image.open(ph.image.path) as im2:
            self.assertEqual(im2.format, "JPEG")

    def test_garbage_fails(self):
        bad = io.BytesIO(b"not-image")
        bad.name = "bad.jpg"
        resp = self.client.post(
            reverse("panel_add_photo", args=[self.prop.id]),
            data={"image": bad},
            format="multipart",
            follow=True,
        )
        self.assertIn("Неподдерживаемый формат", resp.content.decode("utf-8"))
        self.assertFalse(Photo.objects.filter(property=self.prop).exists())
