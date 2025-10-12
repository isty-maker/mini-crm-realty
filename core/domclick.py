"""Domclick feed builder helpers."""
from __future__ import annotations

from typing import Iterable

from .cian import FeedBuildResult, build_cian_feed
from .models import Property


def build_domclick_feed(properties: Iterable[Property]) -> FeedBuildResult:
    """Return a Domclick feed built with the existing CIAN V2 generator.

    Domclick currently accepts the same payload as CIAN Feed Version 2.  The
    helper is kept as a thin layer so provider-specific adjustments can be
    added later without touching the core exporter logic.
    """

    return build_cian_feed(properties)
