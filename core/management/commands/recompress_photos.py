from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from core.models import Photo

try:
    from PIL import Image, ImageFile
except ImportError as exc:  # pragma: no cover - Pillow is required in production
    raise RuntimeError("Pillow is required for recompress_photos") from exc

ImageFile.LOAD_TRUNCATED_IMAGES = True


def encode_jpeg_to_target(img, base_name: str, orig_bytes: bytes) -> ContentFile:
    target = max(150 * 1024, (len(orig_bytes) // 5) if orig_bytes else 150 * 1024)
    lo, hi = 65, 90
    best_buf = None
    while lo <= hi:
        q = (lo + hi) // 2
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
        size = buf.tell()
        if size <= target:
            best_buf = buf
            lo = q + 1
        else:
            hi = q - 1
    if best_buf is None:
        best_buf = BytesIO()
        img.save(best_buf, format="JPEG", quality=75, optimize=True, progressive=True)
    best_buf.seek(0)
    safe_base = base_name or "photo"
    return ContentFile(best_buf.read(), name=f"{safe_base}.jpg")


class Command(BaseCommand):
    help = "Recompress existing photos to ~1/5 size with minimal quality loss."

    def add_arguments(self, parser):
        parser.add_argument("--max", type=int, default=1000, help="Max photos to process")

    def handle(self, *args, **opts):
        qs = Photo.objects.exclude(image="").order_by("id")[: opts["max"]]
        processed = 0
        for ph in qs:
            field_file = ph.image
            if not field_file:
                continue
            try:
                field_file.open("rb")
                orig = field_file.read()
            except Exception as exc:
                self.stderr.write(f"Skip {ph.id}: {exc}")
                continue
            finally:
                try:
                    field_file.close()
                except Exception:
                    pass

            if not orig:
                self.stderr.write(f"Skip {ph.id}: empty file")
                continue

            try:
                img = Image.open(BytesIO(orig)).convert("RGB")
            except Exception as exc:
                self.stderr.write(f"Skip {ph.id}: {exc}")
                continue

            w, h = img.size
            if max(w, h) > 2560:
                ratio = 2560 / float(max(w, h))
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

            base = Path(field_file.name or "photo").stem or "photo"
            try:
                new_content = encode_jpeg_to_target(img, base, orig)
            except Exception as exc:
                self.stderr.write(f"Skip {ph.id}: {exc}")
                continue

            old_name = field_file.name or ""
            new_name = str(Path(old_name or base).with_suffix(".jpg"))
            try:
                ph.image.save(new_name, new_content, save=True)
                if new_name != old_name and old_name:
                    try:
                        field_file.storage.delete(old_name)
                    except Exception:
                        pass
                processed += 1
                self.stdout.write(f"OK {ph.id}")
            except Exception as exc:
                self.stderr.write(f"Skip {ph.id}: {exc}")

        self.stdout.write(self.style.SUCCESS(f"Recompressed: {processed}"))
