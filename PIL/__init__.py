"""Minimal subset of the Pillow package used for tests.

This stub implements only the parts of Pillow that are touched by the
project's code and automated tests (Image.open/new/save/resize/convert).
It is intentionally lightweight so that the codebase can operate in
restricted environments without external binary dependencies.
"""

from . import Image as Image  # noqa: F401
from .Image import LANCZOS, new, open  # noqa: F401

__all__ = ["Image", "LANCZOS", "new", "open"]
