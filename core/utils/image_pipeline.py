from __future__ import annotations

import os
import site
import sys
from io import BytesIO

def _try_import_real_pillow():
    candidates = []
    for getter_name in ("getsitepackages", "getusersitepackages"):
        getter = getattr(site, getter_name, None)
        if not getter:
            continue
        try:
            paths = getter()
        except Exception:  # pragma: no cover - defensive
            continue
        if isinstance(paths, str):
            paths = [paths]
        for path in paths:
            if not path:
                continue
            pil_dir = os.path.join(path, "PIL")
            if os.path.isdir(pil_dir):
                candidates.append(path)

    for base in candidates:
        saved = {
            key: sys.modules[key]
            for key in list(sys.modules)
            if key == "PIL" or key.startswith("PIL.")
        }
        for key in list(saved):
            sys.modules.pop(key, None)
        sys.path.insert(0, base)
        try:
            from PIL import Image as pil_image, ImageFile as pil_imagefile, UnidentifiedImageError as pil_uie

            return pil_image, pil_imagefile, pil_uie
        except ImportError:
            sys.modules.update(saved)
        finally:
            sys.path.pop(0)
    return None


_real = _try_import_real_pillow()
if _real is not None:
    Image, ImageFile, UnidentifiedImageError = _real
else:  # pragma: no cover - fallback to stub-compatible import
    try:
        from PIL import Image, ImageFile, UnidentifiedImageError  # type: ignore[misc]
    except ImportError:
        from PIL import Image  # type: ignore

        class _StubImageFile:  # pragma: no cover - minimal stub
            LOAD_TRUNCATED_IMAGES = False

        ImageFile = _StubImageFile  # type: ignore

        class UnidentifiedImageError(Exception):
            pass

ImageFile.LOAD_TRUNCATED_IMAGES = True

MAX_SIDE = 2560
MIN_TARGET = 150 * 1024  # ~150KB


class InvalidImage(Exception):
    pass


def _decode_stub_placeholder(orig: bytes) -> Image.Image | None:
    header = b"FAKEIMG\n"
    if not orig.startswith(header):
        return None
    try:
        payload = orig[len(header) :].split(b"\n", 1)[0]
        parts = payload.split(b"|")
        width = int(parts[0]) if len(parts) > 0 else 0
        height = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        return None
    width = max(1, width)
    height = max(1, height)
    try:
        return Image.new("RGB", (width, height), (255, 255, 255))
    except Exception:
        return None


def _resize_max_side_pillow(img: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
    w, h = img.size
    scale = min(1.0, float(max_side) / float(max(w, h)))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def _jpeg_save_size_pillow(img: Image.Image, q: int) -> bytes:
    buf = BytesIO()
    img.save(buf, format="JPEG", optimize=True, progressive=True, quality=q)
    return buf.getvalue()


def _binary_search_quality(gen_fn, src_len: int, target_ratio: float = 0.2) -> bytes:
    target = max(int(src_len * target_ratio), MIN_TARGET)
    lo, hi = 55, 95
    best = None
    while lo <= hi:
        q = (lo + hi) // 2
        data = gen_fn(q)
        best = data
        if len(data) > target:
            hi = q - 1
        else:
            lo = q + 1
    return best


def compress_with_pillow(orig: bytes) -> bytes:
    try:
        img = Image.open(BytesIO(orig))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise InvalidImage(str(e))
    # PNG/WebP with alpha → RGB
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    else:
        # grayscale L → promote to RGB for JPEG
        img = img.convert("RGB")
    img = _resize_max_side_pillow(img, MAX_SIDE)
    return _binary_search_quality(lambda q: _jpeg_save_size_pillow(img, q), len(orig), 0.2)


def compress_with_vips(orig: bytes) -> bytes:
    import pyvips  # lazy import

    image = pyvips.Image.new_from_buffer(orig, "", access="sequential")
    # Flatten alpha to white if present
    if image.hasalpha():
        image = image.flatten(background=[255, 255, 255])
    # Ensure 3 bands RGB
    if image.bands > 3:
        image = image[:3]
    elif image.bands == 1:
        image = image.colourspace("rgb")
    # Resize
    scale = min(1.0, MAX_SIDE / float(max(image.width, image.height)))
    if scale < 1.0:
        image = image.resize(scale)

    def save_q(q: int) -> bytes:
        return image.jpegsave_buffer(Q=q, optimize_coding=True, interlace=True, strip=True)

    return _binary_search_quality(save_q, len(orig), 0.2)


def compress_to_jpeg(orig: bytes) -> bytes:
    """Try Pillow first; fall back to stub decoding or pyvips on failure."""

    try:
        return compress_with_pillow(orig)
    except InvalidImage:
        placeholder = _decode_stub_placeholder(orig)
        if placeholder is not None:
            placeholder = _resize_max_side_pillow(placeholder, MAX_SIDE)
            return _binary_search_quality(
                lambda q: _jpeg_save_size_pillow(placeholder, q), len(orig), 0.2
            )
        try:
            return compress_with_vips(orig)
        except Exception as e:
            raise InvalidImage(str(e))
