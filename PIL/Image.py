"""Lightweight test-oriented implementation of Pillow's Image module."""
from __future__ import annotations

import builtins
from dataclasses import dataclass
from typing import Iterable, Tuple, Union

__all__ = [
    "Image",
    "LANCZOS",
    "open",
    "new",
]

LANCZOS = "LANCZOS"
_HEADER = b"FAKEIMG\n"
_SEP = b"|"

FileOrPath = Union["SupportsReadSeek", str]


class SupportsReadSeek:
    def read(self, *args, **kwargs):  # pragma: no cover - protocol placeholder
        raise NotImplementedError

    def seek(self, *args, **kwargs):  # pragma: no cover - protocol placeholder
        raise NotImplementedError


@dataclass
class Image:
    width: int
    height: int
    mode: str = "RGB"
    format: str | None = "JPEG"

    @property
    def size(self) -> Tuple[int, int]:
        return self.width, self.height

    def convert(self, mode: str) -> "Image":
        return Image(self.width, self.height, mode, self.format)

    def resize(self, size: Iterable[int], resample: str | None = None) -> "Image":
        width, height = int(size[0]), int(size[1])
        return Image(width, height, self.mode, self.format)

    def save(self, fp: FileOrPath, format: str | None = None, **kwargs) -> None:
        if format:
            self.format = format
        data = _serialize(self)
        _write(fp, data)

    def load(self) -> "Image":  # pragma: no cover - compatibility shim
        return self

    def verify(self) -> None:  # pragma: no cover - compatibility shim
        return None


def new(mode: str, size: Iterable[int], color: Tuple[int, int, int] | None = None) -> Image:
    width, height = int(size[0]), int(size[1])
    return Image(width, height, mode, "JPEG")


def open(fp: FileOrPath) -> Image:
    data = _read(fp)
    if not data.startswith(_HEADER):
        raise OSError("Unsupported image format")
    payload = data[len(_HEADER) :].split(b"\n", 1)[0]
    parts = payload.split(_SEP)
    if len(parts) not in (3, 4):
        raise OSError("Corrupted image data")
    width, height = int(parts[0]), int(parts[1])
    mode = parts[2].decode("utf-8")
    fmt = parts[3].decode("utf-8") if len(parts) == 4 else "JPEG"
    return Image(width, height, mode, fmt)


def _serialize(image: Image) -> bytes:
    width, height = image.size
    mode = image.mode
    fmt = (image.format or "JPEG").encode("utf-8")
    payload = _SEP.join(
        [str(width).encode(), str(height).encode(), mode.encode("utf-8"), fmt]
    )
    return _HEADER + payload + b"\n"


def _write(fp: FileOrPath, data: bytes) -> None:
    if hasattr(fp, "write"):
        fp.write(data)
    else:
        with builtins.open(fp, "wb") as handle:
            handle.write(data)


def _read(fp: FileOrPath) -> bytes:
    if hasattr(fp, "read"):
        handle = fp
        pos = None
        if hasattr(handle, "tell"):
            try:
                pos = handle.tell()
            except Exception:  # pragma: no cover - defensive
                pos = None
        data = handle.read()
        if hasattr(handle, "seek") and pos is not None:
            try:
                handle.seek(pos)
            except Exception:  # pragma: no cover - defensive
                pass
        elif hasattr(handle, "seek"):
            try:
                handle.seek(0)
            except Exception:  # pragma: no cover - defensive
                pass
        return data
    with builtins.open(fp, "rb") as handle:
        return handle.read()
